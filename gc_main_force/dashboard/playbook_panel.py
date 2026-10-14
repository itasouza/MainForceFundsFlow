"""Contextual playbook: which rule applies to the market right now."""

from __future__ import annotations

from typing import Any

import streamlit as st

from dashboard.i18n import t
from dashboard.playbook import (
    ABSORPTION_NEAR_TICKS,
    OFF_SESSIONS,
    PLAYBOOK_RULES,
    TRIGGER_PRIORITY,
    rule_by_trigger,
)
from dashboard.trade_journal import has_open_trade

_TONE = {
    "neutral_signal": ("#450a0a", "#f87171"),
    "off_session": ("#713f12", "#fde68a"),
    "divergence_detected": ("#713f12", "#fde68a"),
    "price_near_absorption": ("#1e3a5f", "#93c5fd"),
    "in_position": ("#1e3a5f", "#93c5fd"),
    "always": ("#1f2937", "#d1d5db"),
}


def _tick_size(state: dict[str, Any]) -> float:
    meta = state.get("footprint_meta") or {}
    try:
        size = float(meta.get("tick_size") or 0.10)
    except (TypeError, ValueError):
        size = 0.10
    return size if size > 0 else 0.10


def _footprint_10m(state: dict[str, Any], latest: dict[str, Any] | None) -> dict[str, Any]:
    live = (state.get("institutional_footprint") or {}).get("10m") or {}
    if live.get("absorption_level") is not None:
        return live
    if latest:
        closed = (latest.get("institutional_footprint") or {}).get("10m") or {}
        if closed.get("absorption_level") is not None:
            return closed
    return live or {}


# Same lean threshold as MTF cards (components._side_from_norm) so alert sides match UI.
_VISUAL_THR = 0.02


def _tf_side(norm: float, thr: float) -> str:
    if norm > thr:
        return "buy"
    if norm < -thr:
        return "sell"
    return "flat"


def _mf_norms(source: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in ("10m", "30m", "1H"):
        out[key] = float((source.get(key) or {}).get("mf_delta_norm", 0.0))
    return out


def _sides_from_norms(norms: dict[str, float], thr_map: dict[str, float]) -> dict[str, str]:
    return {
        "10m": _tf_side(norms["10m"], thr_map["10m"]),
        "30m": _tf_side(norms["30m"], thr_map["30m"]),
        "1H": _tf_side(norms["1H"], thr_map["1H"]),
    }


def diagnose_neutral(latest: dict[str, Any] | None, state: dict[str, Any]) -> dict[str, Any]:
    """
    Explain why composite is 0 even when short TFs / footprint look one-sided.

    Prefer live open-bar MTF (same as cards). Engine rule: 1H clears first,
    then 30m AND 10m must agree — but only on bar close.
    """
    thr = state.get("thresholds") or {}
    engine_thr = {
        "10m": float(thr.get("threshold_10m", 0.30)),
        "30m": float(thr.get("threshold_30m", 0.20)),
        "1H": float(thr.get("threshold_1h", 0.15)),
    }
    visual_thr = {k: _VISUAL_THR for k in engine_thr}

    live = state.get("mtf_live") or {}
    closed = (latest or {}).get("timeframes") or {}
    # Display sides always match the cards the trader is looking at.
    display_src = live if live else closed
    display_norms = _mf_norms(display_src)
    sides = _sides_from_norms(display_norms, visual_thr)

    empty = {
        "reason": "no_signal",
        "sides": sides,
        "awaiting": "1H",
        "partial": None,
    }
    if not latest and not live:
        return empty

    # If live MF already clears engine thresholds on all TFs, composite is only
    # waiting for bar close — not "mixed".
    if live:
        live_engine = _sides_from_norms(_mf_norms(live), engine_thr)
        lh, lm, lt = live_engine["1H"], live_engine["30m"], live_engine["10m"]
        if lh == lm == lt and lh != "flat":
            return {
                "reason": "live_aligned_wait_close",
                "sides": sides,
                "awaiting": "bar_close",
                "partial": lh,
            }

    # Classify with engine thresholds on the best available source (live > closed).
    classify_norms = _mf_norms(live) if live else _mf_norms(closed)
    eng = _sides_from_norms(classify_norms, engine_thr)
    h, m, tf10 = eng["1H"], eng["30m"], eng["10m"]

    if h == "flat" and m == tf10 and m != "flat":
        return {"reason": "awaiting_1h", "sides": sides, "awaiting": "1H", "partial": m}
    # 10m (and/or 30m) lean but 1H still below engine thr — not "mixed".
    if h == "flat" and (m != "flat" or tf10 != "flat") and not (m != "flat" and tf10 != "flat" and m != tf10):
        lean = m if m != "flat" else tf10
        return {"reason": "awaiting_1h", "sides": sides, "awaiting": "1H", "partial": lean}
    if h != "flat" and (m == "flat" or tf10 == "flat" or m != h or tf10 != h):
        return {"reason": "awaiting_lower_tf", "sides": sides, "awaiting": "10m/30m", "partial": h}
    if h == m == tf10 == "flat":
        # Visual lean can still show buy/sell on cards while engine is flat.
        if sides["1H"] == sides["30m"] == sides["10m"] and sides["1H"] != "flat":
            return {
                "reason": "live_aligned_wait_close",
                "sides": sides,
                "awaiting": "bar_close",
                "partial": sides["1H"],
            }
        return {"reason": "true_flat", "sides": sides, "awaiting": None, "partial": None}
    if h == m == tf10 and h != "flat":
        return {
            "reason": "live_aligned_wait_close",
            "sides": sides,
            "awaiting": "bar_close",
            "partial": h,
        }
    return {"reason": "mixed", "sides": sides, "awaiting": "alignment", "partial": None}


def market_context(
    state: dict[str, Any],
    latest: dict[str, Any] | None,
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    price = state.get("last_price")
    fp = _footprint_10m(state, latest)
    abs_level = fp.get("absorption_level")
    abs_vol = float(fp.get("absorption_volume") or 0.0)
    distance = None
    if price is not None and abs_level is not None:
        distance = abs(float(price) - float(abs_level)) / _tick_size(state)
    session = state.get("active_session") or ""
    if latest is None:
        signal = None
        is_neutral = True
        if state.get("mtf_live"):
            diagnosis = diagnose_neutral(None, state)
            if diagnosis.get("reason") == "no_signal":
                diagnosis = {
                    "reason": "awaiting_first_close",
                    "sides": diagnosis.get("sides")
                    or {"10m": "flat", "30m": "flat", "1H": "flat"},
                    "awaiting": "10m",
                    "partial": None,
                }
        else:
            diagnosis = {
                "reason": "awaiting_first_close",
                "sides": {"10m": "flat", "30m": "flat", "1H": "flat"},
                "awaiting": "10m",
                "partial": None,
            }
    else:
        signal = int(latest.get("composite_signal", 0))
        is_neutral = signal == 0
        diagnosis = (
            diagnose_neutral(latest, state)
            if is_neutral
            else {"reason": "active", "sides": {}, "awaiting": None, "partial": None}
        )
    return {
        "divergence": bool(latest and latest.get("divergence_detected")),
        "neutral": is_neutral,
        "signal": signal,
        "diagnosis": diagnosis,
        "near_absorption": distance is not None and distance <= ABSORPTION_NEAR_TICKS,
        "distance_ticks": distance,
        "absorption_level": abs_level,
        "absorption_volume": abs_vol,
        "last_price": price,
        "off_session": session in OFF_SESSIONS,
        "in_position": has_open_trade(trades),
    }


def active_triggers(ctx: dict[str, Any]) -> list[str]:
    found = ["always"]
    if ctx["neutral"]:
        found.append("neutral_signal")
    if ctx["off_session"]:
        found.append("off_session")
    if ctx["divergence"]:
        found.append("divergence_detected")
    if ctx["near_absorption"]:
        found.append("price_near_absorption")
    if ctx["in_position"]:
        found.append("in_position")
    return found


def primary_rule(ctx: dict[str, Any]) -> dict:
    found = set(active_triggers(ctx))
    for trigger in TRIGGER_PRIORITY:
        if trigger in found:
            return rule_by_trigger(trigger)
    return rule_by_trigger("always")


def badge_html(rule: dict) -> str:
    bg, fg = _TONE.get(rule["trigger"], _TONE["always"])
    label = t("pb.badge", n=rule["id"])
    return (
        f"<span style='background:{bg};color:{fg};font-weight:700;"
        f"padding:.3rem .75rem;border-radius:8px;border:1px solid {fg}'>"
        f"{rule['icon']} {label}</span>"
    )


def _neutral_alert_text(ctx: dict[str, Any]) -> tuple[str, str]:
    """Title + message for rule #6, nuanced when short TFs already lean one way."""
    diag = ctx.get("diagnosis") or {}
    reason = diag.get("reason")
    sides = diag.get("sides") or {}

    def _label(side: str) -> str:
        if side == "buy":
            return t("side.buy")
        if side == "sell":
            return t("side.sell")
        return "—"

    side_txt = (
        f"10m={_label(sides.get('10m', 'flat'))} · "
        f"30m={_label(sides.get('30m', 'flat'))} · "
        f"1H={_label(sides.get('1H', 'flat'))}"
    )
    if reason == "awaiting_first_close":
        return t("alert.wait_close_title"), t("alert.wait_close_msg")
    if reason == "live_aligned_wait_close":
        partial = diag.get("partial") or "buy"
        direction = t("side.buy") if partial == "buy" else t("side.sell")
        return (
            t("alert.wait_live_title"),
            t("alert.wait_live_msg", direction=direction, sides=side_txt),
        )
    if reason == "awaiting_1h":
        partial = diag.get("partial") or "buy"
        direction = t("side.buy") if partial == "buy" else t("side.sell")
        return (
            t("alert.wait_1h_title"),
            t("alert.wait_1h_msg", direction=direction, sides=side_txt),
        )
    if reason == "awaiting_lower_tf":
        partial = diag.get("partial") or "buy"
        direction = t("side.buy") if partial == "buy" else t("side.sell")
        return (
            t("alert.wait_lower_title"),
            t("alert.wait_lower_msg", direction=direction, sides=side_txt),
        )
    if reason == "mixed":
        return t("alert.flat_title"), t("alert.mixed_msg", sides=side_txt)
    return t("alert.flat_title"), t("alert.flat_msg", sides=side_txt)


def render_contextual_alerts(ctx: dict[str, Any]) -> None:
    if ctx["neutral"]:
        title, msg = _neutral_alert_text(ctx)
        # Partial lean / live aligned → amber (wait); true flat / mixed → red
        reason = (ctx.get("diagnosis") or {}).get("reason")
        if reason in (
            "awaiting_1h",
            "awaiting_lower_tf",
            "awaiting_first_close",
            "live_aligned_wait_close",
        ):
            st.warning(f"⏳ **{title}** — {msg}")
        else:
            st.error(f"⛔ **{title}** — {msg}")
        # Footprint ≠ sinal composto: short note when they seem to disagree
        abs_vol = float(ctx.get("absorption_volume") or 0.0)
        if abs_vol != 0 and reason in ("awaiting_1h", "live_aligned_wait_close"):
            st.caption(t("alert.fp_vs_signal"))
    if ctx["off_session"]:
        st.warning(f"🕐 **{t('alert.session_title')}** — {t('alert.session_msg')}")
    if ctx["divergence"]:
        st.warning(f"⚠️ **{t('alert.div_title')}** — {t('alert.div_msg')}")
    if ctx["near_absorption"] and ctx["absorption_level"] is not None and ctx["distance_ticks"] is not None:
        st.info(
            "🎯 **"
            + t("alert.abs_title")
            + "** — "
            + t(
                "alert.abs_msg",
                ticks=f"{ctx['distance_ticks']:.0f}",
                level=f"{float(ctx['absorption_level']):.2f}",
            )
        )
    if ctx["in_position"]:
        st.info(f"🚪 **{t('alert.pos_title')}** — {t('alert.pos_msg')}")


def render_playbook(ctx: dict[str, Any]) -> None:
    st.subheader(t("pb.section"))
    st.caption(t("pb.lead"))
    found = set(active_triggers(ctx))
    for rule in PLAYBOOK_RULES:
        on = rule["trigger"] in found and rule["trigger"] != "always"
        if rule["trigger"] == "always" and found == {"always"}:
            on = True
        bg, fg = _TONE[rule["trigger"]] if on else ("transparent", "#9ca3af")
        border = fg if on else "#374151"
        weight = "700" if on else "500"
        st.markdown(
            f"""
            <div style="border:1px solid {border};background:{bg};border-radius:10px;
                        padding:.65rem .85rem;margin-bottom:.45rem;">
              <div style="font-weight:{weight};color:{fg if on else 'inherit'}">
                {rule['icon']} #{rule['id']} · {t(f"pb.{rule['id']}.title")}
              </div>
              <div style="margin-top:.2rem;opacity:.9">{t(f"pb.{rule['id']}.rule")}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
