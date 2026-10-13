"""Reusable Streamlit UI pieces for the GC Main Force dashboard."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


SIGNAL_LABELS = {
    1: ("LONG BIAS", "#16a34a"),
    -1: ("SHORT BIAS", "#dc2626"),
    0: ("NEUTRAL — PAUSE GRID", "#6b7280"),
}


def render_status_header(state: dict[str, Any]) -> None:
    mode = state.get("mode", "idle")
    live = bool(state.get("live"))
    if mode == "live" and live:
        st.markdown("🟢 **LIVE** — recebendo ticks do NinjaTrader")
    elif mode == "live":
        st.markdown("🟡 **LIVE (sem ticks)** — aguardando NinjaTrader / ZeroMQ")
    elif mode == "backtest":
        st.markdown("🔴 **BACKTEST** — modo CSV")
    else:
        st.markdown("⚪ **IDLE** — engine não conectado")


def render_price_line(state: dict[str, Any]) -> None:
    price = state.get("last_price")
    open_px = state.get("session_open_price")
    if price is None:
        st.metric("Preço GC", "—")
        return
    delta = None
    if open_px:
        delta = f"{((price - open_px) / open_px) * 100:.2f}%"
    st.metric("Preço GC", f"{price:.2f}", delta=delta)


def render_signal_panel(payload: dict[str, Any] | None) -> None:
    if not payload:
        st.info("Aguardando primeiro sinal composto (fechamento 10m).")
        return
    sig = int(payload.get("composite_signal", 0))
    label, color = SIGNAL_LABELS.get(sig, SIGNAL_LABELS[0])
    conf = float(payload.get("confidence_score", 0.0)) * 100
    st.markdown(
        f"""
        <div style="background:{color};color:white;padding:1.4rem 1.2rem;border-radius:12px;text-align:center;">
          <div style="font-size:0.85rem;opacity:0.9;">SINAL COMPOSTO</div>
          <div style="font-size:2rem;font-weight:700;margin:0.25rem 0;">{label}</div>
          <div style="font-size:0.95rem;">Confiança: {conf:.0f}% · {payload.get('timestamp','')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.progress(min(max(conf / 100.0, 0.0), 1.0))


def render_tf_columns(payload: dict[str, Any] | None) -> None:
    if not payload or "timeframes" not in payload:
        st.write("Sem dados MTF.")
        return
    tfs = payload["timeframes"]
    cols = st.columns(3)
    for col, key in zip(cols, ("10m", "30m", "1H")):
        with col:
            data = tfs.get(key, {})
            mf = float(data.get("mf_delta_norm", 0))
            rt = float(data.get("retail_delta_norm", 0))
            abs_delta = float(data.get("mf_delta", 0))
            st.subheader(key)
            color = "#16a34a" if mf >= 0 else "#dc2626"
            st.markdown(f"**MF Δ norm:** `{mf:+.3f}`")
            st.progress(min(abs(mf), 1.0))
            st.caption(f"Retail Δ norm: `{rt:+.3f}`")
            st.markdown(f"MF Δ absoluto: **{abs_delta:+,.0f}** contratos")
            # Trend from previous would need prev; approximate with sign of mf
            arrow = "↑" if mf > 0.02 else ("↓" if mf < -0.02 else "→")
            st.markdown(
                f"<span style='color:{color};font-size:1.4rem'>{arrow}</span>",
                unsafe_allow_html=True,
            )


def render_divergence(payload: dict[str, Any] | None) -> None:
    if not payload:
        return
    if payload.get("divergence_detected"):
        msg = payload.get("divergence_message") or "Divergência MF vs Varejo"
        st.warning(
            f"⚠️ {msg}\n\nSugestão: considere pausar novas entradas do grid na direção da tendência."
        )


def build_price_chart(bars: list[dict], signal_log: list[dict]) -> go.Figure:
    if not bars:
        fig = go.Figure()
        fig.update_layout(title="Sem barras 10m ainda", height=420, template="plotly_dark")
        return fig

    df = pd.DataFrame(bars)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.72, 0.28],
        vertical_spacing=0.03,
    )
    fig.add_trace(
        go.Candlestick(
            x=df["timestamp"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="GC 10m",
        ),
        row=1,
        col=1,
    )

    # Volume colored by MF vs retail dominance
    colors = [
        "#58a6ff" if abs(r.mf_delta_norm) >= abs(r.retail_delta_norm) else "#bc8cff"
        for r in df.itertuples()
    ]
    fig.add_trace(
        go.Bar(x=df["timestamp"], y=df["volume"], marker_color=colors, name="Volume"),
        row=2,
        col=1,
    )

    # Signal markers mapped by timestamp proximity to bar close
    if signal_log:
        slog = pd.DataFrame(signal_log)
        slog["timestamp"] = pd.to_datetime(slog["timestamp"])
        for sig, symbol, color, name in (
            (1, "triangle-up", "#16a34a", "LONG"),
            (-1, "triangle-down", "#dc2626", "SHORT"),
            (0, "circle", "#9ca3af", "NEUTRO"),
        ):
            sub = slog.loc[slog["composite_signal"] == sig]
            if sub.empty:
                continue
            # place markers near close of matching bar if possible
            y = []
            for ts in sub["timestamp"]:
                match = df.loc[(df["timestamp"] - ts).abs().idxmin()]
                y.append(float(match["close"]))
            fig.add_trace(
                go.Scatter(
                    x=sub["timestamp"],
                    y=y,
                    mode="markers",
                    marker=dict(symbol=symbol, size=12, color=color),
                    name=name,
                ),
                row=1,
                col=1,
            )

    fig.update_layout(
        height=520,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        margin=dict(l=20, r=20, t=30, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def signal_log_table(log: list[dict]) -> pd.DataFrame:
    if not log:
        return pd.DataFrame()
    rows = []
    for p in log[-30:]:
        tfs = p.get("timeframes") or {}
        sig = int(p.get("composite_signal", 0))
        emoji = {1: "🟢", -1: "🔴", 0: "⚪"}.get(sig, "⚪")
        rows.append(
            {
                "Timestamp": p.get("timestamp"),
                "Sinal": f"{emoji} {sig}",
                "Conf %": round(float(p.get("confidence_score", 0)) * 100, 1),
                "MF 10m": (tfs.get("10m") or {}).get("mf_delta_norm"),
                "MF 30m": (tfs.get("30m") or {}).get("mf_delta_norm"),
                "MF 1H": (tfs.get("1H") or {}).get("mf_delta_norm"),
                "Divergência": "Y" if p.get("divergence_detected") else "N",
                "Sessão": p.get("session", ""),
            }
        )
    return pd.DataFrame(rows).iloc[::-1]
