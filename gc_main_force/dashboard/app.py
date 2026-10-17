"""Streamlit real-time dashboard — GC Main Force Flow Monitor."""

from __future__ import annotations

import json
import sys
import time
from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dashboard.auth import require_login
from dashboard.components import (
    fmt_br,
    build_price_chart,
    render_divergence,
    render_mf_footprint_section,
    render_mtf_vs_footprint_note,
    render_price_line,
    render_signal_panel,
    render_status_header,
    render_tf_columns,
    signal_badge,
    signal_log_table,
)
from dashboard.i18n import regime_label, session_label, source_label, t
from dashboard.playbook_panel import (
    badge_html,
    market_context,
    primary_rule,
    render_contextual_alerts,
    render_playbook,
)
from dashboard.trade_journal import (
    load_memory,
    open_trade_button,
    render_close_form,
    render_stats,
    render_trade_form,
)
from python_engine.config import get_config
from python_engine.incremental_engine import run_incremental_on_ticks
from python_engine.regime_classifier import load_ai_controls, save_ai_controls
from python_engine.signal_engine import active_session
from python_engine.state_store import EngineStateStore
from python_engine.tick_receiver import load_ticks_csv

st.set_page_config(
    page_title="Main Force Flow",
    page_icon="🥇",
    layout="wide",
)
require_login()

cfg = get_config()
STATE_PATH = _ROOT / cfg["state_file"]


ENGINE_STALE_SEC = 30


def load_engine_state() -> dict:
    return EngineStateStore(STATE_PATH).load()


def state_age_seconds(path: Path) -> float | None:
    """Seconds since the engine last wrote the state file. None if the file is missing."""
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None


def format_age(seconds: float) -> str:
    whole = max(0, int(seconds))
    if whole < 60:
        return t("age.sec", n=whole)
    minutes = whole // 60
    if minutes < 60:
        return t("age.min", n=minutes)
    hours, mins = divmod(minutes, 60)
    return t("age.hour", h=hours, m=mins)


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
if st.session_state.get("lang") not in ("pt", "en"):
    st.session_state["lang"] = "pt"
THEMES = {
    "default": ("#0e1117", "#262730", "#f5b301"),
    "navy": ("#0b1220", "#111a2e", "#f5b301"),
    "black": ("#000000", "#0a0a0a", "#f5b301"),
    "graphite": ("#1a1d23", "#23272f", "#f5b301"),
    "emerald": ("#0a1410", "#10201a", "#34d399"),
}
if st.session_state.get("theme_name") not in THEMES:
    st.session_state["theme_name"] = "default"
if st.session_state.get("ui_mode") not in ("live", "backtest"):
    st.session_state["ui_mode"] = "live"

st.sidebar.title(t("sidebar.title"))
if st.sidebar.button(t("login.out")):
    st.session_state["logged_in"] = False
    st.rerun()
ui_mode = st.sidebar.selectbox(
    t("view_mode"),
    ["live", "backtest"],
    format_func=lambda code: t(f"mode.{code}"),
    key="ui_mode",
)
pause = st.sidebar.checkbox(t("pause_live"), value=False)

with st.sidebar.expander(t("exp.thresholds"), expanded=False):
    mf_thr = st.slider(t("mf_min"), 1, 50, int(cfg["mf_fixed_threshold_contracts"]))
    thr_1h = st.slider(t("thr_1h"), 0.05, 0.50, float(cfg["threshold_1h"]), 0.01)
    thr_30 = st.slider(t("thr_30"), 0.05, 0.50, float(cfg["threshold_30m"]), 0.01)
    thr_10 = st.slider(t("thr_10"), 0.05, 0.60, float(cfg["threshold_10m"]), 0.01)
    roll_h = st.slider(t("roll_h"), 1, 48, int(cfg["rolling_window_hours"]))

with st.sidebar.expander(t("exp.footprint"), expanded=False):
    show_footprint = st.checkbox(
        t("show_fp"),
        value=True,
        help=t("show_fp_help"),
    )


AI_CONTROLS_PATH = _ROOT / str(cfg.get("ai_controls_file", "ai_controls.json"))
_controls = load_ai_controls(AI_CONTROLS_PATH)
with st.sidebar.expander(t("exp.ai"), expanded=False):
    ai_enabled = st.toggle(t("ai_on"), value=bool(_controls.get("ai_enabled", True)))
    force_opt = st.selectbox(
        t("force_regime"),
        options=["auto", "0", "1", "2"],
        format_func=lambda code: t(f"regime_opt.{code}"),
        index=0
        if _controls.get("force_regime") is None
        else int(_controls.get("force_regime", 1)) + 1,
    )
    pause_grid = st.toggle(
        t("pause_signal"),
        value=bool(_controls.get("pause_grid", False)),
        help=t("pause_signal_help"),
    )
    if st.button(t("apply_ai")):
        force_regime = None if force_opt == "auto" else int(force_opt)
        save_ai_controls(
            AI_CONTROLS_PATH,
            {
                "ai_enabled": ai_enabled,
                "force_regime": force_regime,
                "pause_grid": pause_grid,
            },
        )
        st.success(t("ai_saved"))

session_filter = st.sidebar.selectbox(
    t("session_filter"),
    ["all", "asian", "london", "new_york", "off_hours"],
    format_func=session_label,
)

overrides = {
    "mf_fixed_threshold_contracts": mf_thr,
    "threshold_1h": thr_1h,
    "threshold_30m": thr_30,
    "threshold_10m": thr_10,
    "rolling_window_hours": roll_h,
}

uploaded = None
if ui_mode == "backtest":
    uploaded = st.sidebar.file_uploader(t("csv_upload"), type=["csv"])
    if uploaded and st.sidebar.button(t("process_csv")):
        st.session_state["bt_state"] = run_local_backtest(uploaded.getvalue(), overrides)

# ---------- Dashboard body ----------
# sleep()+st.rerun() used to block the session and intermittently stack a full
# duplicate page in the browser. Refresh only this fragment instead.
form_open = bool(
    st.session_state.get("journal_form_open") or st.session_state.get("journal_close_open")
)
_auto_refresh = ui_mode == "live" and not pause and not form_open


def _tile(label: str, value: str, sub: str = "") -> str:
    sub_html = f"<div style='font-size:.7rem;opacity:.55;margin-top:2px'>{sub}</div>" if sub else ""
    return (
        "<div style='background:rgba(128,128,128,.10);border-radius:10px;padding:.5rem .65rem'>"
        f"<div style='font-size:.68rem;letter-spacing:.06em;text-transform:uppercase;opacity:.6'>{label}</div>"
        f"<div style='font-size:.95rem;font-weight:600;margin-top:2px'>{value}</div>"
        f"{sub_html}</div>"
    )


def _render_dashboard() -> None:
    if ui_mode == "backtest" and "bt_state" in st.session_state:
        state = st.session_state["bt_state"]
    else:
        state = load_engine_state()

    log = filter_log_by_session(list(state.get("signal_log") or []), session_filter)
    latest = state.get("latest_signal")
    if session_filter != "all" and log:
        latest = log[-1]
    memory = load_memory(_ROOT)
    mentor = market_context(state, latest, memory["trades"])
    active_rule = primary_rule(mentor)

    # ---------- Header (barra compacta) ----------
    head_left, head_right = st.columns([2, 3], vertical_alignment="center")
    with head_right:
        if st.session_state.get("theme_name") not in THEMES:
            st.session_state["theme_name"] = "default"
        lang_col, theme_col = st.columns([1, 2], vertical_alignment="center")
        with lang_col:
            st.pills(
                t("language"),
                ["pt", "en"],
                format_func=lambda code: t(f"lang.{code}"),
                selection_mode="single",
                key="lang",
                label_visibility="collapsed",
            )
        with theme_col:
            theme_name = st.pills(
                t("theme"),
                list(THEMES),
                format_func=lambda code: t(f"theme.{code}"),
                selection_mode="single",
                key="theme_name",
                label_visibility="collapsed",
            ) or "default"
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
    state_age = state_age_seconds(STATE_PATH) if ui_mode == "live" else None
    engine_down = ui_mode == "live" and (state_age is None or state_age > ENGINE_STALE_SEC)
    if engine_down:
        status = t("status.engine_down")
    elif mode == "live" and state.get("live"):
        status = t("status.live")
    elif mode == "live":
        status = t("status.live_stale")
    elif mode == "backtest":
        status = t("status.backtest")
    else:
        status = t("status.idle")
    age_html = ""
    if ui_mode == "live" and state_age is not None and not engine_down:
        age_html = (
            f"<span style='font-size:.75rem;opacity:.7'>{t('status.engine_ok', age=format_age(state_age))}</span>"
        )

    # Header badge: composite is closed-bar only. When live MF is already
    # aligned (rule #7), show early bias instead of "NEUTRO — PAUSAR".
    diag = mentor.get("diagnosis") or {}
    if diag.get("reason") == "live_aligned_wait_close":
        partial = diag.get("partial") or "buy"
        if partial == "sell":
            sig_txt, sig_color = t("signal.live_sell"), "#dc2626"
        else:
            sig_txt, sig_color = t("signal.live_buy"), "#16a34a"
    elif diag.get("reason") == "mf_vs_price":
        sig_txt, sig_color = t("signal.mf_vs_price"), "#f59e0b"
    elif latest:
        sig_label, sig_color = signal_badge(int(latest.get("composite_signal", 0)))
        sig_txt = f"{sig_label} · {float(latest.get('confidence_score', 0)) * 100:.0f}%"
    else:
        sig_txt, sig_color = t("awaiting_signal"), "#6b7280"

    price = state.get("last_price")
    open_px = state.get("session_open_price")
    if price is None:
        px_html = "—"
    else:
        px_html = f"<b style='font-size:1.15rem'>{price:.2f}</b>"
        if open_px:
            chg = (price - open_px) / open_px * 100
            px_html += f" <span style='color:{'#16a34a' if chg >= 0 else '#dc2626'}'>{chg:+.2f}%</span>"

    regime_txt = (
        f"{regime.get('regime', '—')} · {regime_label(regime.get('label'), regime.get('regime'))}"
    )
    thr_txt = (
        f"<span style='font-size:.8rem'>1H {thr.get('threshold_1h', '—')}<br>"
        f"30m {thr.get('threshold_30m', '—')}<br>10m {thr.get('threshold_10m', '—')}</span>"
    )
    grid_paused = bool(thr.get("grid_paused"))

    grid_html = (
        f"<span style='color:#dc2626'>{t('yes')}</span>"
        if grid_paused
        else f"<span style='color:#16a34a'>{t('no')}</span>"
    )
    session_name = session_label(state.get("active_session")) if state.get("active_session") else "—"
    tiles = "".join(
        [
            _tile(t("tile.price"), px_html),
            _tile(t("tile.session"), session_name, t("ticks_n", n=state.get("tick_count", 0))),
            _tile(t("tile.regime"), regime_txt, t("source_line", source=source_label(regime.get("source", "—")))),
            _tile(t("tile.paused"), grid_html, t("mf_floor", n=thr.get("mf_fixed_threshold_contracts", "—"))),
        ]
    )
    ts = f" · {fmt_br(latest.get('timestamp'))} ({t('brasilia')})" if latest else ""
    symbol = (
        state.get("symbol")
        or (latest or {}).get("symbol")
        or "—"
    )
    feed = state.get("tick_source") or ""
    feed_txt = f" · {feed}" if feed else ""

    with head_left:
        st.markdown(
            "<div style='display:flex;flex-wrap:wrap;align-items:center;gap:.5rem 1rem'>"
            "<span style='font-size:1.3rem;font-weight:700'>🥇 Main Force Flow</span>"
            f"<span style='background:#1e293b;color:#f8fafc;font-weight:700;padding:.25rem .7rem;"
            f"border-radius:8px;border:1px solid #38bdf8;letter-spacing:.04em'>{symbol}</span>"
            f"<span style='font-weight:600'>{status}</span>"
            f"<span style='background:{sig_color};color:#fff;font-weight:700;padding:.3rem .9rem;border-radius:8px'>{sig_txt}</span>"
            f"{badge_html(active_rule)}"
            f"{age_html}"
            f"<span style='font-size:.75rem;opacity:.55'>{ts.lstrip(' · ')}{feed_txt}</span>"
            "</div>",
            unsafe_allow_html=True,
        )
    if ui_mode == "live":
        ticks_now = int(state.get("tick_count") or 0)
        if st.session_state.get("_ticks_mark") != ticks_now:
            st.session_state["_ticks_mark"] = ticks_now
            st.session_state["_ticks_mark_at"] = time.time()
        ticks_quiet = time.time() - float(st.session_state.get("_ticks_mark_at") or time.time())
    else:
        ticks_quiet = 0.0
    tape_stopped = ui_mode == "live" and not engine_down and ticks_quiet > ENGINE_STALE_SEC
    if engine_down:
        age_txt = format_age(state_age) if state_age is not None else t("age.unknown")
        st.error(t("alert.engine_down", age=age_txt))
    elif tape_stopped:
        st.warning(t("alert.tape_stopped", age=format_age(ticks_quiet)))
    tiles_col, limits_col, trade_col = st.columns([4.2, 1.05, 1.55], vertical_alignment="center")
    with tiles_col:
        st.markdown(
            "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:.5rem'>"
            f"{tiles}</div>",
            unsafe_allow_html=True,
        )
    with limits_col:
        st.markdown(_tile(t("tile.thresholds"), thr_txt), unsafe_allow_html=True)
    with trade_col:
        open_trade_button(memory["trades"])
    render_trade_form(_ROOT, state)
    render_close_form(_ROOT, state)
    if state.get("live") and not state.get("latest_signal"):
        st.info(t("info.waiting_close"))
    if not state.get("live") and (state.get("tick_count") or 0) == 0:
        st.warning(t("warn.no_ticks"))
    render_contextual_alerts(mentor)
    render_divergence(latest)

    # ---------- Abas ----------
    tab_op, tab_chart, tab_log, tab_mentor = st.tabs(
        [t("tab.op"), t("tab.chart"), t("tab.log"), t("tab.mentor")]
    )

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
        st.subheader(t("mtf.title"))
        render_tf_columns(
            latest,
            live_mtf=state.get("mtf_live"),
            bars_10m=list(state.get("bars_10m") or []),
            last_price=float(state["last_price"]) if state.get("last_price") is not None else None,
        )
        if show_footprint:
            render_mtf_vs_footprint_note(latest, fp_bundle, live_mtf=state.get("mtf_live"))
            st.markdown("<div style='height:2rem'></div>", unsafe_allow_html=True)
            footprint_tf = st.pills(
                t("fp.timeframe"),
                ["10m", "30m", "1H", "10m + 30m + 1H"],
                default="10m",
                selection_mode="single",
                key="fp_tf",
            ) or "10m"
            if footprint_tf == "10m + 30m + 1H":
                # 3 footprints lado a lado (mesma ordem dos cartões MTF)
                for col, tf in zip(st.columns(3, gap="small"), ("10m", "30m", "1H")):
                    with col:
                        render_mf_footprint_section(
                            fp_bundle,
                            selected_tf=tf,
                            footprint_meta=state.get("footprint_meta"),
                            ninja_price=state.get("last_price"),
                            compact=True,
                        )
            else:
                render_mf_footprint_section(
                    fp_bundle,
                    selected_tf=footprint_tf,
                    footprint_meta=state.get("footprint_meta"),
                    ninja_price=state.get("last_price"),
                )

    with tab_chart:
        st.subheader(t("chart.title"))
        fig = build_price_chart(list(state.get("bars_10m") or []), log)
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)

    with tab_log:
        table = signal_log_table(log)
        if table.empty:
            st.info(t("log.empty"))
        else:
            st.dataframe(table, use_container_width=True, height=480)
            st.download_button(
                t("log.export"),
                data=table.to_csv(index=False).encode("utf-8"),
                file_name="gc_mf_signal_log.csv",
                mime="text/csv",
            )

    with tab_mentor:
        sub_playbook, sub_journal, sub_stats = st.tabs(
            [t("tab.playbook"), t("tab.journal"), t("tab.stats")]
        )
        with sub_playbook:
            render_playbook(mentor)
        with sub_journal:
            st.caption(t("journal.near_limits"))
        with sub_stats:
            render_stats(_ROOT)


@st.fragment(run_every=timedelta(seconds=3) if _auto_refresh else None, key="mf_dashboard")
def _dashboard_fragment() -> None:
    _render_dashboard()


_dashboard_fragment()
