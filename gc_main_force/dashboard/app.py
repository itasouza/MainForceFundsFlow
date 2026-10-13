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
    render_price_line,
    render_signal_panel,
    render_status_header,
    render_tf_columns,
    signal_log_table,
)
from python_engine.config import get_config
from python_engine.main import compute_signals_from_ticks
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
    tmp = _ROOT / "_upload_ticks.csv"
    tmp.write_bytes(csv_bytes)
    ticks = load_ticks_csv(tmp)
    local_cfg = get_config(overrides)
    payloads, all_bars = compute_signals_from_ticks(ticks, local_cfg)
    bars = []
    b10 = all_bars["10m"].tail(int(local_cfg["chart_bars_display"]))
    for ts, row in b10.iterrows():
        bars.append(
            {
                "timestamp": pd.Timestamp(ts).isoformat(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "mf_delta_norm": float(row["mf_delta_norm"]),
                "retail_delta_norm": float(row["retail_delta_norm"]),
            }
        )
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
        "bars_10m": bars,
        "active_session": payloads[-1].get("session") if payloads else None,
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
            "Recebendo ticks do NinjaTrader. Aguarde o fechamento de barras 10m "
            "(e depois 30m/1H) para o sinal composto completo."
        )
with c2:
    render_price_line(state)
with c3:
    sess = state.get("active_session") or "—"
    st.metric("Sessão ativa (ET)", str(sess).upper())
    st.caption(f"Ticks buffer: {state.get('tick_count', 0)}")

st.divider()

# ---------- Main signal ----------
left, right = st.columns([1.2, 1])
with left:
    render_signal_panel(latest)
with right:
    render_divergence(latest)

st.subheader("Análise Multi-Timeframe")
render_tf_columns(latest)

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

st.caption(
    "Arquitetura: NinjaTrader (ticks ZMQ :5556) → Python engine → sinais ZMQ :5555 + este dashboard. "
    f"Estado: `{STATE_PATH.name}`"
)

# Auto-refresh in live view
if ui_mode.startswith("Live") and not pause:
    time.sleep(1.5)
    st.rerun()
