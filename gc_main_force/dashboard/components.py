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


def build_institutional_footprint_chart(
    primary: dict[str, Any] | None,
    *,
    context_30m: dict[str, Any] | None = None,
    tf_label: str = "10m",
) -> go.Figure:
    """
    Horizontal net-MF volume by price (last closed bar).

    Green = net buying; red = net selling. Optional lighter 30m overlay for context.
    """
    fig = go.Figure()
    primary = primary or {}
    levels = list(primary.get("price_levels") or [])
    nets = list(primary.get("net_mf_vol") or [])
    buys = list(primary.get("mf_buy_vol") or [])
    sells = list(primary.get("mf_sell_vol") or [])
    high = primary.get("high")
    low = primary.get("low")

    if not levels or not nets:
        fig.update_layout(
            title=f"Sem footprint MF na última barra {tf_label}",
            height=380,
            template="plotly_dark",
            margin=dict(l=20, r=20, t=40, b=20),
        )
        return fig

    colors = ["#16a34a" if n >= 0 else "#dc2626" for n in nets]
    hover = [
        (
            f"${lv:.2f}<br>Net: {n:+.0f}<br>Buy: {b:.0f} · Sell: {s:.0f}"
        )
        for lv, n, b, s in zip(
            levels,
            nets,
            buys if len(buys) == len(levels) else [0.0] * len(levels),
            sells if len(sells) == len(levels) else [0.0] * len(levels),
        )
    ]
    fig.add_trace(
        go.Bar(
            y=levels,
            x=nets,
            orientation="h",
            marker_color=colors,
            name=f"Net MF {tf_label}",
            hovertext=hover,
            hoverinfo="text",
            text=[f"{n:+.0f}" for n in nets],
            textposition="outside",
        )
    )

    # Lighter 30m context (when primary is not already 30m)
    if context_30m and tf_label != "30m":
        c_levels = list(context_30m.get("price_levels") or [])
        c_nets = list(context_30m.get("net_mf_vol") or [])
        if c_levels and c_nets:
            fig.add_trace(
                go.Bar(
                    y=c_levels,
                    x=c_nets,
                    orientation="h",
                    marker_color="rgba(148, 163, 184, 0.35)",
                    name="Net MF 30m (contexto)",
                    hoverinfo="skip",
                    opacity=0.55,
                )
            )

    abs_level = primary.get("absorption_level")
    abs_vol = float(primary.get("absorption_volume") or 0.0)
    if abs_level is not None:
        # Price on Y → horizontal guide at absorption (annotation uses $ price)
        fig.add_hline(
            y=float(abs_level),
            line_dash="dash",
            line_color="#fbbf24",
            annotation_text=f"Nível de Absorção: ${float(abs_level):.2f}",
            annotation_position="top right",
            annotation_font=dict(color="#fbbf24", size=12),
        )

    y0 = float(low) if low is not None else min(levels)
    y1 = float(high) if high is not None else max(levels)
    pad = max(0.2, (y1 - y0) * 0.08 if y1 > y0 else 0.5)
    fig.update_layout(
        title=f"🐉 Rastro Institucional ({tf_label}) — net MF por preço",
        height=440,
        template="plotly_dark",
        margin=dict(l=20, r=40, t=50, b=20),
        xaxis_title="Net Main Force (contratos)",
        yaxis_title="Preço GC",
        yaxis=dict(range=[y0 - pad, y1 + pad]),
        barmode="overlay",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        bargap=0.12,
    )
    if abs_level is not None and abs_vol != 0:
        fig.add_annotation(
            x=0,
            y=float(abs_level),
            text=f"{abs_vol:+.0f} cts",
            showarrow=False,
            font=dict(color="#fbbf24", size=11),
            xanchor="left",
            yshift=10,
        )
    return fig


def render_mf_footprint_section(
    footprint_bundle: dict[str, Any] | None,
    *,
    selected_tf: str = "10m",
) -> None:
    """
    Dashboard block: institutional footprint + grid decision table.

    ``footprint_bundle`` = {\"10m\": {...}, \"30m\": {...}, \"1H\": {...}} from state/payload.
    """
    st.subheader("🐉 Rastro Institucional (Footprint de Grandes Lotes)")
    st.caption(
        "Onde e com que agressão o dinheiro grande está entrando? "
        "(proxy de preço/volume MF no CME — sem seats de corretora.)"
    )
    bundle = footprint_bundle or {}
    primary = bundle.get(selected_tf) or {}
    ctx30 = bundle.get("30m") or {}

    abs_level = primary.get("absorption_level")
    abs_vol = float(primary.get("absorption_volume") or 0.0)
    if abs_level is not None and abs_vol != 0:
        side = "compra (suporte)" if abs_vol > 0 else "venda (resistência)"
        st.markdown(
            f"**Nível de Absorção: `${float(abs_level):.2f}` "
            f"({abs_vol:+.0f} contratos net — {side})** · TF `{selected_tf}`"
        )
    else:
        st.info("Sem absorção MF na última barra fechada deste TF — fluxo ainda sem nó claro.")

    fig = build_institutional_footprint_chart(
        primary, context_30m=ctx30, tf_label=selected_tf
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Como interpretar o Footprint para o Grid", expanded=False):
        st.markdown(
            """
| Cenário | Ação no Grid |
|---|---|
| Absorção **positiva** (compra) **abaixo** do preço | ✅ Grid de compra — há “chão” institucional |
| Absorção **negativa** (venda) **acima** do preço | ✅ Grid de venda — há “teto” institucional |
| Compra embaixo + venda em cima | ⚠️ Range — grid conservador, lotes menores |
| Sem nó claro / volume espalhado | ❌ Pausar grid — falta convicção institucional |

**Pontos de atenção:** não coloque limites **exatamente** no `absorption_level`
(desloque 2–4 ticks de $0.10). O campo JSON `institutional_footprint` é o contrato
para a Strategy / EA futura.
            """
        )


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
