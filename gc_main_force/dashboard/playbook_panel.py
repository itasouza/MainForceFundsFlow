"""Contextual playbook: which rule applies to the market right now."""

from __future__ import annotations

from typing import Any

import streamlit as st

from dashboard.components import _price_candle_side, enrich_mtf_ohlc
from dashboard.i18n import t, translate_divergence
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
    "live_aligned_bias": ("#14532d", "#4ade80"),
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

    live_raw = state.get("mtf_live") or {}
    live = enrich_mtf_ohlc(
        live_raw,
        bars_10m=list(state.get("bars_10m") or []),
        last_price=float(state["last_price"]) if state.get("last_price") is not None else None,
    )
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

    def _price_sides(src: dict[str, Any]) -> dict[str, str]:
        out: dict[str, str] = {}
        for key in ("10m", "30m", "1H"):
            row = src.get(key) or {}
            out[key] = _price_candle_side(
                float(row.get("open") or 0.0),
                float(row.get("close") or 0.0),
            )
        return out

    def _mf_vs_price_conflict(mf_sides: dict[str, str], px_sides: dict[str, str]) -> bool:
        """True when at least one TF has MF lean opposite to red/green candle."""
        for key in ("10m", "30m", "1H"):
            m, p = mf_sides.get(key, "flat"), px_sides.get(key, "flat")
            if m != "flat" and p != "flat" and m != p:
                return True
        return False

    # If live MF already clears engine thresholds on all TFs — but only treat as
    # early-entry bias when price candles are not fighting that lean.
    if live:
        live_engine = _sides_from_norms(_mf_norms(live), engine_thr)
        lh, lm, lt = live_engine["1H"], live_engine["30m"], live_engine["10m"]
        if lh == lm == lt and lh != "flat":
            px = _price_sides(live)
            if _mf_vs_price_conflict(live_engine, px):
                return {
                    "reason": "mf_vs_price",
                    "sides": sides,
                    "price_sides": px,
                    "awaiting": "price_confirm",
                    "partial": lh,
                }
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
            px = _price_sides(live) if live else {"10m": "flat", "30m": "flat", "1H": "flat"}
            if _mf_vs_price_conflict(sides, px):
                return {
                    "reason": "mf_vs_price",
                    "sides": sides,
                    "price_sides": px,
                    "awaiting": "price_confirm",
                    "partial": sides["1H"],
                }
            return {
                "reason": "live_aligned_wait_close",
                "sides": sides,
                "awaiting": "bar_close",
                "partial": sides["1H"],
            }
        return {"reason": "true_flat", "sides": sides, "awaiting": None, "partial": None}
    if h == m == tf10 and h != "flat":
        px = _price_sides(live) if live else {"10m": "flat", "30m": "flat", "1H": "flat"}
        if live and _mf_vs_price_conflict({"10m": tf10, "30m": m, "1H": h}, px):
            return {
                "reason": "mf_vs_price",
                "sides": sides,
                "price_sides": px,
                "awaiting": "price_confirm",
                "partial": h,
            }
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
        "divergence_message": (latest or {}).get("divergence_message"),
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
    diag_reason = (ctx.get("diagnosis") or {}).get("reason")
    if ctx["neutral"]:
        # Live MF already clears all TF engine thresholds → early bias (rule #7),
        # not the hard "don't trade" of rule #6.
        if diag_reason == "live_aligned_wait_close":
            found.append("live_aligned_bias")
        else:
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


def _direction_word(side: str | None) -> str:
    return t("side.buy") if side == "buy" else t("side.sell")


def _decision(ctx: dict[str, Any]) -> tuple[str, str] | None:
    """One sentence: the action that matters right now."""
    trigger = primary_rule(ctx)["trigger"]
    diag = ctx.get("diagnosis") or {}
    reason = diag.get("reason")
    partial = diag.get("partial") or "buy"
    direction = _direction_word(partial)
    sides = diag.get("sides") or {}

    if trigger == "off_session":
        return "warning", t("alert.now.session")
    if trigger == "live_aligned_bias":
        return "success", t("alert.now.live", direction=direction)
    if trigger == "divergence_detected":
        return "warning", translate_divergence(ctx.get("divergence_message"))
    if trigger == "price_near_absorption" and ctx.get("absorption_level") is not None:
        return "info", t(
            "alert.now.abs",
            ticks=f"{float(ctx['distance_ticks']):.0f}",
            level=f"{float(ctx['absorption_level']):.2f}",
        )
    if trigger == "in_position":
        return "info", t("alert.now.pos")
    if trigger != "neutral_signal":
        return None
    if reason == "awaiting_first_close":
        return "warning", t("alert.now.wait_close")
    if reason == "mf_vs_price":
        return "warning", t("alert.now.mf_price", direction=direction)
    if reason == "awaiting_1h":
        return "warning", t("alert.now.wait_1h", direction=direction)
    if reason == "awaiting_lower_tf":
        cards_agree = (
            sides.get("10m") == sides.get("30m") == sides.get("1H") == partial
        )
        key = "alert.now.wait_cards" if cards_agree else "alert.now.wait_lower"
        return "warning", t(key, direction=direction)
    if reason == "mixed":
        return "error", t("alert.now.mixed")
    return "error", t("alert.now.flat")


def render_contextual_alerts(ctx: dict[str, Any]) -> None:
    decision = _decision(ctx)
    if decision is None:
        return
    kind, text = decision
    if kind == "success":
        st.success(text)
    elif kind == "error":
        st.error(text)
    elif kind == "info":
        st.info(text)
    else:
        st.warning(text)
    # The exit of a trade already open is the only extra fact on this screen.
    if ctx["in_position"] and primary_rule(ctx)["trigger"] != "in_position":
        st.caption(t("alert.note.pos"))


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
