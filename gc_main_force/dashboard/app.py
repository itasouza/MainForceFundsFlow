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
    SIGNAL_LABELS,
    fmt_br,
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
        "footprint_meta": snap.get("footprint_meta"),
        "active_session": payloads[-1].get("session") if payloads else None,
        "engine": "incremental",
        "regime": snap.get("regime"),
        "thresholds": snap.get("thresholds"),
    }


# ---------- Sidebar ----------
st.sidebar.title("Controles")
THEMES = {
    "Padrão": ("#0e1117", "#262730", "#f5b301"),
    "Azul-marinho": ("#0b1220", "#111a2e", "#f5b301"),
    "Preto": ("#000000", "#0a0a0a", "#f5b301"),
    "Grafite": ("#1a1d23", "#23272f", "#f5b301"),
    "Esmeralda": ("#0a1410", "#10201a", "#34d399"),
}
ui_mode = st.sidebar.selectbox(
    "Modo de visualização",
    ["Live Mode (NinjaTrader / engine)", "Backtest Mode (CSV)"],
)
pause = st.sidebar.checkbox("Pausar atualizações ao vivo", value=False)

with st.sidebar.expander("Thresholds", expanded=False):
    mf_thr = st.slider("Main Force min. contratos (GC)", 1, 50, int(cfg["mf_fixed_threshold_contracts"]))
    thr_1h = st.slider("Threshold 1H", 0.05, 0.50, float(cfg["threshold_1h"]), 0.01)
    thr_30 = st.slider("Threshold 30m", 0.05, 0.50, float(cfg["threshold_30m"]), 0.01)
    thr_10 = st.slider("Threshold 10m", 0.05, 0.60, float(cfg["threshold_10m"]), 0.01)
    roll_h = st.slider("Janela percentil (horas)", 1, 48, int(cfg["rolling_window_hours"]))

with st.sidebar.expander("Footprint", expanded=False):
    show_footprint = st.checkbox(
        "Mostrar Rastro Institucional (LHB)",
        value=True,
        help="Mapa por preço: onde o fluxo agride (Lee-Ready). Sinal MF continua com threshold fixo.",
    )


AI_CONTROLS_PATH = _ROOT / str(cfg.get("ai_controls_file", "ai_controls.json"))
_controls = load_ai_controls(AI_CONTROLS_PATH)
with st.sidebar.expander("IA — Regime / Kill Switch", expanded=False):
    ai_enabled = st.toggle("IA de regime ativa", value=bool(_controls.get("ai_enabled", True)))
    force_opt = st.selectbox(
        "Forçar regime manual",
        options=["auto", "0 — Chop", "1 — Standard/Trend", "2 — High Vol/News"],
        index=0
        if _controls.get("force_regime") is None
        else int(_controls.get("force_regime", 1)) + 1,
    )
    pause_grid = st.toggle(
        "Pausar sinal (override)",
        value=bool(_controls.get("pause_grid", False)),
        help="Kill switch humano: força pausa do sinal / novas entradas independentemente da IA.",
    )
    if st.button("Aplicar controles IA"):
        force_regime = None if force_opt.startswith("auto") else int(force_opt[0])
        save_ai_controls(
            AI_CONTROLS_PATH,
            {
                "ai_enabled": ai_enabled,
                "force_regime": force_regime,
                "pause_grid": pause_grid,
            },
        )
        st.success("Controles salvos — aplicados no próximo fechamento 1H.")

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

# ---------- Header (barra compacta) ----------
head_left, head_right = st.columns([2, 3], vertical_alignment="center")
with head_right:
    theme_name = st.pills(
        "Tema",
        list(THEMES),
        default="Padrão",
        selection_mode="single",
        key="theme_name",
        label_visibility="collapsed",
    ) or "Padrão"
theme_bg, theme_side, theme_accent = THEMES[theme_name]
st.markdown(
    "<style>.block-container{padding-top:2.5rem;padding-bottom:1rem}"
    "div[data-testid='stVerticalBlock']{gap:0.6rem}"
    "[data-testid='stHeader']{height:2.5rem;min-height:2.5rem;background:transparent}"
    f".stApp,[data-testid='stAppViewContainer']{{background:{theme_bg}}}"
    f"[data-testid='stSidebar'],[data-testid='stSidebar']>div{{background:{theme_side}}}"
    f"[data-baseweb='tab-highlight']{{background:{theme_accent}!important}}"
    f"button[role='tab'][aria-selected='true']{{color:{theme_accent}!important}}"
    "[data-testid='stButtonGroup']{flex-wrap:wrap;justify-content:flex-end}"
    "[data-testid='stStatusWidget'],"
    "[data-testid='stAppDeployButton'],[data-testid='stMainMenu']{display:none!important}</style>",
    unsafe_allow_html=True,
)

regime = state.get("regime") or {}
thr = state.get("thresholds") or {}
mode = state.get("mode", "idle")
if mode == "live" and state.get("live"):
    status = "🟢 LIVE"
elif mode == "live":
    status = "🟡 LIVE (sem ticks)"
elif mode == "backtest":
    status = "🔴 BACKTEST"
else:
    status = "⚪ IDLE"

if latest:
    sig_label, sig_color = SIGNAL_LABELS.get(int(latest.get("composite_signal", 0)), SIGNAL_LABELS[0])
    sig_txt = f"{sig_label} · {float(latest.get('confidence_score', 0)) * 100:.0f}%"
else:
    sig_txt, sig_color = "AGUARDANDO SINAL", "#6b7280"

price = state.get("last_price")
open_px = state.get("session_open_price")
if price is None:
    px_html = "—"
else:
    px_html = f"<b style='font-size:1.15rem'>{price:.2f}</b>"
    if open_px:
        chg = (price - open_px) / open_px * 100
        px_html += f" <span style='color:{'#16a34a' if chg >= 0 else '#dc2626'}'>{chg:+.2f}%</span>"


regime_txt = f"{regime.get('regime', '—')} · {regime.get('label', '—')}"
thr_txt = (
    f"<span style='font-size:.8rem'>1H {thr.get('threshold_1h', '—')}<br>"
    f"30m {thr.get('threshold_30m', '—')}<br>10m {thr.get('threshold_10m', '—')}</span>"
)
grid_paused = bool(thr.get("grid_paused"))


def _tile(label: str, value: str, sub: str = "") -> str:
    sub_html = f"<div style='font-size:.7rem;opacity:.55;margin-top:2px'>{sub}</div>" if sub else ""
    return (
        "<div style='background:rgba(128,128,128,.10);border-radius:10px;padding:.5rem .65rem'>"
        f"<div style='font-size:.68rem;letter-spacing:.06em;text-transform:uppercase;opacity:.6'>{label}</div>"
        f"<div style='font-size:.95rem;font-weight:600;margin-top:2px'>{value}</div>"
        f"{sub_html}</div>"
    )


grid_html = (
    "<span style='color:#dc2626'>SIM</span>" if grid_paused else "<span style='color:#16a34a'>NÃO</span>"
)
tiles = "".join(
    [
        _tile("Preço GC", px_html),
        _tile("Sessão (ET)", str(state.get("active_session") or "—").upper(), f"{state.get('tick_count', 0)} ticks"),
        _tile("Regime IA", regime_txt, f"fonte: {regime.get('source', '—')}"),
        _tile("Sinal pausado", grid_html, f"MF floor {thr.get('mf_fixed_threshold_contracts', '—')} cts"),
        _tile("Thresholds", thr_txt),
    ]
)
ts = f" · {fmt_br(latest.get('timestamp'))} (Brasília)" if latest else ""

with head_left:
  st.markdown(
    "<div style='display:flex;flex-wrap:wrap;align-items:center;gap:.5rem 1rem'>"
    "<span style='font-size:1.3rem;font-weight:700'>🥇 GC Main Force Flow</span>"
    f"<span style='font-weight:600'>{status}</span>"
    f"<span style='background:{sig_color};color:#fff;font-weight:700;padding:.3rem .9rem;border-radius:8px'>{sig_txt}</span>"
    f"<span style='font-size:.75rem;opacity:.55'>{ts.lstrip(' · ')}</span>"
    "</div>",
    unsafe_allow_html=True,
  )
st.markdown(
    "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:.5rem;margin-bottom:.8rem'>"
    f"{tiles}</div>",
    unsafe_allow_html=True,
)
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
render_divergence(latest)

# ---------- Abas ----------
tab_op, tab_chart, tab_log = st.tabs(["Operação", "Gráficos", "Log de sinais"])

fp_bundle = None
if show_footprint:
    # Live heartbeat prefers open-bar map; fall back to latest signal payload
    fp_bundle = state.get("institutional_footprint")
    if not fp_bundle or not any(
        (fp_bundle.get(tf) or {}).get("price_levels") for tf in ("10m", "30m", "1H")
    ):
        if latest and latest.get("institutional_footprint"):
            fp_bundle = latest.get("institutional_footprint")

with tab_op:
    st.subheader("Análise Multi-Timeframe")
    render_tf_columns(latest)
    if show_footprint:
        st.markdown("<div style='height:2rem'></div>", unsafe_allow_html=True)
        footprint_tf = st.pills(
            "Timeframe do Footprint",
            ["10m", "30m", "1H"],
            default="10m",
            selection_mode="single",
            key="fp_tf",
        ) or "10m"
        render_mf_footprint_section(
            fp_bundle,
            selected_tf=footprint_tf,
            footprint_meta=state.get("footprint_meta"),
            ninja_price=state.get("last_price"),
        )

with tab_chart:
    st.subheader("Preço GC (10m) + marcadores de sinal")
    fig = build_price_chart(list(state.get("bars_10m") or []), log)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)

with tab_log:
    table = signal_log_table(log)
    if table.empty:
        st.info("Sem sinais ainda.")
    else:
        st.dataframe(table, use_container_width=True, height=480)
        st.download_button(
            "Exportar log CSV",
            data=table.to_csv(index=False).encode("utf-8"),
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
