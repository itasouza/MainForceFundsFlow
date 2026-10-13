"""Reusable Streamlit UI pieces for the GC Main Force dashboard."""

from __future__ import annotations

import re
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


BR_TZ = "America/Sao_Paulo"


def fmt_br(ts: Any) -> str:
    """UTC (ISO, ex.: 2026-10-13T04:10:00Z) -> 13/10/2026 01:10 (horário de Brasília)."""
    if not ts:
        return ""
    try:
        t = pd.Timestamp(ts)
        t = t.tz_localize("UTC") if t.tzinfo is None else t
        return t.tz_convert(BR_TZ).strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return str(ts)


def _series_br(values: Any) -> pd.Series:
    """Série de timestamps UTC -> horário de Brasília (naive, para o Plotly)."""
    return pd.to_datetime(values, utc=True).dt.tz_convert(BR_TZ).dt.tz_localize(None)


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
          <div style="font-size:0.95rem;">Confiança: {conf:.0f}% · {fmt_br(payload.get('timestamp'))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.progress(min(max(conf / 100.0, 0.0), 1.0))


_BUY, _SELL, _FLAT = "#16a34a", "#dc2626", "#6b7280"


def _diverging_bar(value: float, color: str, scale: float = 1.0) -> str:
    """Barra centrada no zero: positivo cresce p/ direita, negativo p/ esquerda."""
    pct = min(abs(value) / scale, 1.0) * 50
    side = "left:50%;" if value >= 0 else f"right:50%;"
    return (
        "<div style='position:relative;height:10px;background:#374151;border-radius:5px;margin:4px 0 6px'>"
        "<div style='position:absolute;left:50%;top:-2px;width:2px;height:14px;background:#9ca3af'></div>"
        f"<div style='position:absolute;{side}width:{pct:.1f}%;height:10px;background:{color};border-radius:5px'></div>"
        "</div>"
    )


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
            if mf > 0.02:
                color, arrow, label = _BUY, "↑", "COMPRA"
            elif mf < -0.02:
                color, arrow, label = _SELL, "↓", "VENDA"
            else:
                color, arrow, label = _FLAT, "→", "NEUTRO"
            rt_color = _BUY if rt > 0.02 else (_SELL if rt < -0.02 else _FLAT)
            st.markdown(
                f"""
                <div style="border:1px solid {color};border-radius:10px;padding:0.5rem 0.8rem;">
                  <div style="display:flex;justify-content:space-between;align-items:baseline;">
                    <b>{key}</b>
                    <span style="color:{color};font-weight:700;font-size:0.9rem;">{arrow} {label}</span>
                  </div>
                  <div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-top:0.2rem;">
                    <span><span style="opacity:.6">MF</span> <b style="color:{color}">{mf:+.3f}</b></span>
                    <span><span style="opacity:.6">Retail</span> <b style="color:{rt_color}">{rt:+.3f}</b></span>
                  </div>
                  {_diverging_bar(mf, color)}
                  <div style="font-size:0.75rem;opacity:.8;">MF Δ: <b>{abs_delta:+,.0f}</b> cts</div>
                </div>
                """,
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
    df["timestamp"] = _series_br(df["timestamp"])
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
        slog["timestamp"] = _series_br(slog["timestamp"])
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
    fig.update_xaxes(tickformat="%d/%m %H:%M")
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
            text=[f"{n:+.0f}" if n else "" for n in nets],
            textposition="outside",
            textfont=dict(size=12),
            cliponaxis=False,
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
            annotation_text=(
                f"Absorção ${float(abs_level):.2f}"
                + (f" · {abs_vol:+.0f} cts" if abs_vol else "")
            ),
            annotation_position="top right",
            annotation_font=dict(color="#fbbf24", size=13),
        )

    y0 = float(low) if low is not None else min(levels)
    y1 = float(high) if high is not None else max(levels)
    pad = max(0.2, (y1 - y0) * 0.08 if y1 > y0 else 0.5)
    fig.update_layout(
        height=380,
        template="plotly_dark",
        margin=dict(l=10, r=60, t=40, b=40),
        xaxis=dict(
            title="Net Main Force (contratos)",
            zeroline=True,
            zerolinecolor="#9ca3af",
            zerolinewidth=1,
            gridcolor="rgba(148,163,184,0.15)",
        ),
        yaxis=dict(
            title="",
            range=[y0 - pad, y1 + pad],
            tickformat=".1f",
            dtick=0.5,
            gridcolor="rgba(148,163,184,0.10)",
        ),
        barmode="overlay",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1.0, font=dict(size=12)),
        bargap=0.25,
        font=dict(size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def decide_grid_from_footprint(
    *,
    ninja_price: float | None,
    absorption_level: float | None,
    absorption_volume: float,
    n_levels: int,
    tick_size: float = 0.10,
) -> dict[str, Any]:
    """
    Compare Ninja last price vs absorption node and return a clear Grid action.

    Returns keys: action, title, detail, tone (success|warning|error|info),
    limit_hint (suggested limit away from absorption).
    """
    if ninja_price is None:
        return {
            "action": "WAIT",
            "title": "Aguardando preço do Ninja",
            "detail": "Sem last_price no estado — confira se o engine está recebendo ticks.",
            "tone": "info",
            "limit_hint": None,
        }
    if n_levels <= 0 or absorption_level is None or float(absorption_volume) == 0.0:
        return {
            "action": "PAUSE",
            "title": "⏸ SEM SINAL — AGUARDAR",
            "detail": (
                f"Preço Ninja ${float(ninja_price):.2f}, mas ainda não há nó de absorção "
                "claro no Footprint. Não force entrada manual."
            ),
            "tone": "error",
            "limit_hint": None,
        }

    px = float(ninja_price)
    lvl = float(absorption_level)
    net = float(absorption_volume)
    offset = 3 * float(tick_size)  # 3 ticks de $0.10
    dist = px - lvl

    # Buy absorption (net+) acting as floor under / at price
    if net > 0 and px >= lvl:
        hint = lvl - offset
        return {
            "action": "BUY",
            "title": "🟢 VIÉS DE COMPRA",
            "detail": (
                f"Preço Ninja ${px:.2f} está **acima** da absorção de compra "
                f"${lvl:.2f} ({net:+.0f} cts) → há chão institucional "
                f"({abs(dist):.2f} abaixo do mercado). "
                f"Operação manual: priorize compras / defesas nessa região."
            ),
            "tone": "buy",
            "limit_hint": hint,
        }

    # Sell absorption (net-) acting as ceiling above / at price
    if net < 0 and px <= lvl:
        hint = lvl + offset
        return {
            "action": "SELL",
            "title": "🔴 VIÉS DE VENDA",
            "detail": (
                f"Preço Ninja ${px:.2f} está **abaixo** da absorção de venda "
                f"${lvl:.2f} ({net:+.0f} cts) → há teto institucional "
                f"({abs(dist):.2f} acima do mercado). "
                f"Operação manual: priorize vendas / defesas nessa região."
            ),
            "tone": "sell",
            "limit_hint": hint,
        }

    # Absorption on the "wrong" side relative to price → cautious / range
    if net > 0 and px < lvl:
        return {
            "action": "CAUTION",
            "title": "⚠️ CAUTELA — não forçar compra",
            "detail": (
                f"Preço Ninja ${px:.2f} está **abaixo** da absorção de compra "
                f"${lvl:.2f}. O chão ficou acima do mercado — risco de range/rejeição."
            ),
            "tone": "warning",
            "limit_hint": lvl - offset,
        }
    return {
        "action": "CAUTION",
        "title": "⚠️ CAUTELA — não forçar venda",
        "detail": (
            f"Preço Ninja ${px:.2f} está **acima** da absorção de venda "
            f"${lvl:.2f}. O teto ficou abaixo do mercado — evite vender agressivo."
        ),
        "tone": "warning",
        "limit_hint": lvl + offset,
    }


def render_mf_footprint_section(
    footprint_bundle: dict[str, Any] | None,
    *,
    selected_tf: str = "10m",
    footprint_meta: dict[str, Any] | None = None,
    ninja_price: float | None = None,
) -> None:
    """
    Dashboard block: institutional footprint + automatic Grid recommendation.

    ``ninja_price`` = last_price from engine (same print the Ninja chart shows).
    """
    st.markdown(f"##### 🐉 Rastro Institucional — Footprint {selected_tf}")
    bundle = footprint_bundle or {}
    primary = bundle.get(selected_tf) or {}
    ctx30 = bundle.get("30m") or {}
    meta = footprint_meta or {}
    tick_size = float((meta or {}).get("tick_size") or primary.get("tick_size") or 0.10)

    live = bool(primary.get("live"))
    source = str(primary.get("source") or "—")
    n_levels = len(primary.get("price_levels") or [])
    max_lot = float(primary.get("max_lot") or 0.0)
    abs_level = primary.get("absorption_level")
    abs_vol = float(primary.get("absorption_volume") or 0.0)

    # Prefer live Ninja last; fall back to bar close from footprint
    px = float(ninja_price) if ninja_price is not None else (
        float(primary["close"]) if primary.get("close") is not None else None
    )

    decision = decide_grid_from_footprint(
        ninja_price=px,
        absorption_level=float(abs_level) if abs_level is not None else None,
        absorption_volume=abs_vol,
        n_levels=n_levels,
        tick_size=tick_size,
    )

    # --- Big action card (what to do) ---
    # buy = green, sell = red (never paint sell as "success" green)
    tone = decision["tone"]
    box = {
        "buy": ("#14532d", "#86efac"),
        "sell": ("#7f1d1d", "#fca5a5"),
        "success": ("#14532d", "#86efac"),
        "warning": ("#713f12", "#fde68a"),
        "error": ("#450a0a", "#f87171"),
        "info": ("#1e3a5f", "#93c5fd"),
    }.get(tone, ("#1e3a5f", "#93c5fd"))
    title = decision["title"]
    action = decision["action"]
    if action == "BUY":
        short = "Chão institucional abaixo do mercado. Priorize compras nessa região."
    elif action == "SELL":
        short = "Teto institucional acima do mercado. Priorize vendas nessa região."
    elif action == "CAUTION" and "compra" in title:
        short = "O chão ficou acima do preço — risco de range. Não force compra."
    elif action == "CAUTION":
        short = "O teto ficou abaixo do preço. Evite vender agressivo."
    else:
        short = re.sub(r"\*\*(.+?)\*\*", lambda m: m.group(1), decision["detail"])
    st.markdown(
        f"""
        <div style="background:{box[0]};border:1px solid {box[1]};color:#f8fafc;
                    padding:0.8rem 1rem;border-radius:10px;margin:0.2rem 0 0.6rem 0;">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:0.5rem;flex-wrap:wrap;">
            <span style="font-size:1.25rem;font-weight:700;">{title}</span>
            <span style="background:rgba(255,255,255,0.18);border-radius:999px;padding:0.15rem 0.7rem;
                         font-size:0.85rem;font-weight:700;">⏱ Barra de {selected_tf}</span>
          </div>
          <div style="font-size:0.95rem;line-height:1.4;margin-top:0.3rem;">{short}</div>
          <div style="font-size:0.7rem;opacity:0.65;margin-top:0.4rem;">
            leitura manual · baseada no footprint da barra de {selected_tf} · não é ordem automática
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    def _fp_tile(label: str, value: str, sub: str = "") -> str:
        sub_html = f"<div style='font-size:.72rem;opacity:.6'>{sub}</div>" if sub else ""
        return (
            "<div style='background:rgba(128,128,128,.10);border-radius:8px;padding:.45rem .7rem'>"
            f"<div style='font-size:.65rem;letter-spacing:.06em;text-transform:uppercase;opacity:.6'>{label}</div>"
            f"<div style='font-size:1.05rem;font-weight:600'>{value}</div>{sub_html}</div>"
        )

    dist_txt = f"{px - float(abs_level):+.2f}" if (px is not None and abs_level is not None) else "—"
    hint_val = decision.get("limit_hint")
    st.markdown(
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:.5rem;margin-bottom:.6rem'>"
        + _fp_tile("Preço Ninja", f"${px:.2f}" if px is not None else "—")
        + _fp_tile(
            "Absorção",
            f"${float(abs_level):.2f}" if abs_level is not None else "—",
            f"{abs_vol:+.0f} cts" if abs_vol else "",
        )
        + _fp_tile("Distância", dist_txt, "preço − absorção")
        + _fp_tile("Zona sugerida", f"${float(hint_val):.2f}" if hint_val is not None else "—", "~3 ticks da absorção")
        + _fp_tile("Barra", "AO VIVO" if live else "fechada", f"{n_levels} níveis · lote máx {max_lot:.0f}")
        + "</div>",
        unsafe_allow_html=True,
    )

    if n_levels == 0:
        st.warning(
            "Footprint sem nós ainda. Aguarde ticks ou rode Backtest com o CSV de amostra."
        )

    fig = build_institutional_footprint_chart(
        primary, context_30m=ctx30, tf_label=selected_tf
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Regras e filtros desta leitura", expanded=False):
        if meta:
            st.caption(
                f"Filtro footprint: "
                f"{'MF≥' + str(meta.get('mf_fixed')) if meta.get('mf_only') else '≥' + str(meta.get('fp_min', 1)) + ' cts'} "
                f"· source=`{source}` · sinal MF AND fixo≥{meta.get('mf_fixed', '—')}"
            )
        st.markdown(
            """
| Comparação automática | Leitura para operação **manual** |
|---|---|
| Absorção **compra** (net+) **≤** preço Ninja | ✅ Viés de compra (chão abaixo) |
| Absorção **venda** (net−) **≥** preço Ninja | ✅ Viés de venda (teto acima) |
| Nó do lado “errado” vs preço | ⚠️ Cautela — não forçar |
| Sem nó / sem preço | ⏸ Aguardar |

Isso **não** dispara ordem. Cruze com o **sinal composto** (3 TFs) no topo do painel.
Zona de entrada: **2–4 ticks** longe do `absorption_level`.
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
                "Data/hora (BRT)": fmt_br(p.get("timestamp")),
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
