"""Streamlit real-time dashboard — GC Main Force Flow Monitor."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dashboard.components import (
    build_price_chart,
    render_divergence,
    render_mf_footprint_section,
    render_price_line,
    render_signal_panel,
    render_status_header,
    render_tf_columns,
    signal_log_table,
)
from python_engine.config import get_config
from python_engine.incremental_engine import run_incremental_on_ticks
from python_engine.regime_classifier import load_ai_controls, save_ai_controls
from python_engine.signal_engine import active_session
from python_engine.state_store import EngineStateStore
from python_engine.tick_receiver import load_ticks_csv

st.set_page_config(
    page_title="GC Main Force Flow",
    page_icon="🥇",
    layout="wide",
)

cfg = get_config()
STATE_PATH = _ROOT / cfg["state_file"]


def load_engine_state() -> dict:
    return EngineStateStore(STATE_PATH).load()


def filter_log_by_session(log: list[dict], session_filter: str) -> list[dict]:
    if session_filter == "all":
        return log
    return [p for p in log if p.get("session") == session_filter]


def run_local_backtest(csv_bytes: bytes, overrides: dict) -> dict:
    """Replay CSV via incremental engine so institutional_footprint matches live."""
    tmp = _ROOT / "_upload_ticks.csv"
    tmp.write_bytes(csv_bytes)
    ticks = load_ticks_csv(tmp)
    local_cfg = get_config(overrides)
    payloads: list[dict] = []
    engine = run_incremental_on_ticks(
        ticks,
        local_cfg,
        on_signal=lambda p: payloads.append(p),
    )
    snap = engine.snapshot_state()
    for p in payloads:
        p["session"] = active_session(pd.Timestamp(p["timestamp"]), local_cfg["sessions"])
    return {
        "mode": "backtest",
        "live": False,
        "tick_count": len(ticks),
        "last_price": float(ticks["price"].iloc[-1]) if len(ticks) else None,
        "session_open_price": float(ticks["price"].iloc[0]) if len(ticks) else None,
        "latest_signal": payloads[-1] if payloads else None,
        "signal_log": payloads[-50:],
        "bars_10m": snap.get("bars_10m") or [],
        "institutional_footprint": snap.get("institutional_footprint")
        or ((payloads[-1].get("institutional_footprint") if payloads else None) or {}),
        "active_session": payloads[-1].get("session") if payloads else None,
        "engine": "incremental",
        "regime": snap.get("regime"),
        "thresholds": snap.get("thresholds"),
    }


# ---------- Sidebar ----------
st.sidebar.title("Controles")
ui_mode = st.sidebar.selectbox(
    "Modo de visualização",
    ["Live Mode (NinjaTrader / engine)", "Backtest Mode (CSV)"],
)

mf_thr = st.sidebar.slider("Main Force min. contratos (GC)", 1, 50, int(cfg["mf_fixed_threshold_contracts"]))
thr_1h = st.sidebar.slider("Threshold 1H", 0.05, 0.50, float(cfg["threshold_1h"]), 0.01)
thr_30 = st.sidebar.slider("Threshold 30m", 0.05, 0.50, float(cfg["threshold_30m"]), 0.01)
thr_10 = st.sidebar.slider("Threshold 10m", 0.05, 0.60, float(cfg["threshold_10m"]), 0.01)
roll_h = st.sidebar.slider("Janela percentil (horas)", 1, 48, int(cfg["rolling_window_hours"]))
pause = st.sidebar.checkbox("Pausar atualizações ao vivo", value=False)
show_footprint = st.sidebar.toggle(
    "Mostrar Rastro Institucional",
    value=True,
    help="Footprint MF por preço (última barra fechada) — onde o dinheiro grande agride.",
)
footprint_tf = st.sidebar.selectbox(
    "Timeframe do Footprint",
    options=["10m", "30m", "1H"],
    index=0,
)

st.sidebar.markdown("---")
st.sidebar.subheader("IA — Regime / Kill Switch")
AI_CONTROLS_PATH = _ROOT / str(cfg.get("ai_controls_file", "ai_controls.json"))
_controls = load_ai_controls(AI_CONTROLS_PATH)
ai_enabled = st.sidebar.toggle("IA de regime ativa", value=bool(_controls.get("ai_enabled", True)))
force_opt = st.sidebar.selectbox(
    "Forçar regime manual",
    options=["auto", "0 — Chop", "1 — Standard/Trend", "2 — High Vol/News"],
    index=0
    if _controls.get("force_regime") is None
    else int(_controls.get("force_regime", 1)) + 1,
)
pause_grid = st.sidebar.toggle(
    "Pausar grid (override)",
    value=bool(_controls.get("pause_grid", False)),
    help="Kill switch humano: força pausa de novas entradas independentemente da IA.",
)
if st.sidebar.button("Aplicar controles IA"):
    force_regime = None if force_opt.startswith("auto") else int(force_opt[0])
    save_ai_controls(
        AI_CONTROLS_PATH,
        {
            "ai_enabled": ai_enabled,
            "force_regime": force_regime,
            "pause_grid": pause_grid,
        },
    )
    st.sidebar.success("Controles salvos — aplicados no próximo fechamento 1H.")

session_filter = st.sidebar.selectbox(
    "Filtro de sessão",
    ["all", "asian", "london", "new_york", "off_hours"],
    format_func=lambda x: {
        "all": "Todas",
        "asian": "Asian (18:00–01:00 ET)",
        "london": "London (01:00–08:00 ET)",
        "new_york": "New York (08:00–17:00 ET)",
        "off_hours": "Off hours",
    }.get(x, x),
)

overrides = {
    "mf_fixed_threshold_contracts": mf_thr,
    "threshold_1h": thr_1h,
    "threshold_30m": thr_30,
    "threshold_10m": thr_10,
    "rolling_window_hours": roll_h,
}

uploaded = None
if ui_mode.startswith("Backtest"):
    uploaded = st.sidebar.file_uploader("CSV de ticks", type=["csv"])
    if uploaded and st.sidebar.button("Processar CSV"):
        st.session_state["bt_state"] = run_local_backtest(uploaded.getvalue(), overrides)

# ---------- Load state ----------
if ui_mode.startswith("Backtest") and "bt_state" in st.session_state:
    state = st.session_state["bt_state"]
else:
    state = load_engine_state()

log = filter_log_by_session(list(state.get("signal_log") or []), session_filter)
latest = state.get("latest_signal")
if session_filter != "all" and log:
    latest = log[-1]

# ---------- Header ----------
st.title("🥇 Gold Futures (GC) — Main Force Flow Monitor")
c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    render_status_header(state)
    if state.get("live") and not state.get("latest_signal"):
        st.info(
            "Recebendo ticks do NinjaTrader. O sinal composto aparece após o "
            "fechamento da primeira barra 10m (e alinhamento 30m/1H)."
        )
    if not state.get("live") and (state.get("tick_count") or 0) == 0:
        st.warning(
            "Sem ticks no estado. Confirme no Ninja: indicador GC Tick Publisher (TCP) "
            "com LISTENING e tps>0, e o engine Python em modo live."
        )
with c2:
    render_price_line(state)
with c3:
    sess = state.get("active_session") or "—"
    st.metric("Sessão ativa (ET)", str(sess).upper())
    st.caption(f"Ticks buffer: {state.get('tick_count', 0)}")

regime = state.get("regime") or {}
thr = state.get("thresholds") or {}
r1, r2, r3 = st.columns(3)
with r1:
    rid = regime.get("regime", "—")
    st.metric("Regime IA", f"{rid} · {regime.get('label', '—')}")
    st.caption(f"Fonte: {regime.get('source', '—')}")
with r2:
    st.metric("Grid pausado", "SIM" if thr.get("grid_paused") else "NÃO")
    st.caption(f"MF floor: {thr.get('mf_fixed_threshold_contracts', '—')} cts")
with r3:
    st.metric(
        "Thresholds ativos",
        f"1H {thr.get('threshold_1h', '—')} | 30m {thr.get('threshold_30m', '—')} | 10m {thr.get('threshold_10m', '—')}",
    )

st.divider()

# ---------- Main signal ----------
left, right = st.columns([1.2, 1])
with left:
    render_signal_panel(latest)
with right:
    render_divergence(latest)

st.subheader("Análise Multi-Timeframe")
render_tf_columns(latest)

if show_footprint:
    fp_bundle = state.get("institutional_footprint")
    if not fp_bundle and latest:
        fp_bundle = latest.get("institutional_footprint")
    render_mf_footprint_section(fp_bundle, selected_tf=footprint_tf)

st.subheader("Preço GC (10m) + marcadores de sinal")
fig = build_price_chart(list(state.get("bars_10m") or []), log)
st.plotly_chart(fig, use_container_width=True)

st.sidebar.subheader("Log de sinais")
table = signal_log_table(log)
if table.empty:
    st.sidebar.info("Sem sinais ainda.")
else:
    st.sidebar.dataframe(table, use_container_width=True, height=360)
    csv_bytes = table.to_csv(index=False).encode("utf-8")
    st.sidebar.download_button(
        "Exportar log CSV",
        data=csv_bytes,
        file_name="gc_mf_signal_log.csv",
        mime="text/csv",
    )

engine_mode = state.get("engine") or "—"
st.caption(
    "Arquitetura: NinjaTrader (TCP :5556) → Python engine incremental → sinais ZMQ :5555 + dashboard. "
    f"Estado: `{STATE_PATH.name}` · engine={engine_mode}"
)

# Auto-refresh in live view (3s — state disk writes are heartbeat/10m, not 0.5s)
if ui_mode.startswith("Live") and not pause:
    time.sleep(3.0)
    st.rerun()
