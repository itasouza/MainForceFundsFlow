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


def market_context(
    state: dict[str, Any],
    latest: dict[str, Any] | None,
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    price = state.get("last_price")
    fp = _footprint_10m(state, latest)
    abs_level = fp.get("absorption_level")
    distance = None
    if price is not None and abs_level is not None:
        distance = abs(float(price) - float(abs_level)) / _tick_size(state)
    session = state.get("active_session") or ""
    signal = int(latest.get("composite_signal", 0)) if latest else None
    return {
        "divergence": bool(latest and latest.get("divergence_detected")),
        "neutral": signal == 0,
        "near_absorption": distance is not None and distance <= ABSORPTION_NEAR_TICKS,
        "distance_ticks": distance,
        "absorption_level": abs_level,
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


def render_contextual_alerts(ctx: dict[str, Any]) -> None:
    if ctx["neutral"]:
        st.error(f"⛔ **{t('alert.flat_title')}** — {t('alert.flat_msg')}")
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
