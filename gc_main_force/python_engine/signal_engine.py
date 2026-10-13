"""Composite MTF signal, confidence, divergence detection, session helpers."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def detect_divergence(timeframes: dict[str, dict[str, float]]) -> tuple[bool, str]:
    """
    Opposite signs of MF vs retail on 30m or 1H → divergence.

    Returns (flag, human message).
    """
    for key in ("30m", "1H"):
        if key not in timeframes:
            continue
        mf = float(timeframes[key]["mf_delta_norm"])
        rt = float(timeframes[key]["retail_delta_norm"])
        if abs(mf) < 0.05 or abs(rt) < 0.05:
            continue
        if mf > 0 and rt < 0:
            return True, (
                f"DIVERGENCE ({key}): Retail selling, Main Force accumulating"
            )
        if mf < 0 and rt > 0:
            return True, (
                f"DIVERGENCE ({key}): Retail buying, Main Force distributing"
            )
    return False, ""


def _bias_1h(mf: float, thr: float) -> int:
    if mf > thr:
        return 1
    if mf < -thr:
        return -1
    return 0


def compute_confidence(
    timeframes: dict[str, dict[str, float]],
    signal: int,
    threshold_1h: float,
    threshold_30m: float,
    threshold_10m: float,
) -> float:
    if signal == 0:
        return 0.0
    h = timeframes["1H"]["mf_delta_norm"]
    m = timeframes["30m"]["mf_delta_norm"]
    t = timeframes["10m"]["mf_delta_norm"]
    sign = float(signal)
    mag = (
        min(abs(h) / max(threshold_1h, 1e-6), 1.5)
        + min(abs(m) / max(threshold_30m, 1e-6), 1.5)
        + min(abs(t) / max(threshold_10m, 1e-6), 1.5)
    ) / 4.5
    align = 1.0 if np.sign(h) == np.sign(m) == np.sign(t) == sign else 0.6
    div, _ = detect_divergence(timeframes)
    penalty = 0.85 if div else 1.0
    return float(np.clip(mag * align * penalty, 0.0, 1.0))


def composite_signal_from_context(
    timeframes: dict[str, dict[str, float]],
    threshold_1h: float = 0.15,
    threshold_30m: float = 0.20,
    threshold_10m: float = 0.30,
) -> tuple[int, float]:
    """Return (signal in {-1,0,1}, confidence)."""
    bias = _bias_1h(timeframes["1H"]["mf_delta_norm"], threshold_1h)
    if bias == 0:
        return 0, 0.0
    m = timeframes["30m"]["mf_delta_norm"]
    t = timeframes["10m"]["mf_delta_norm"]
    if bias == 1 and not (m > threshold_30m and t >= threshold_10m):
        return 0, 0.0
    if bias == -1 and not (m < -threshold_30m and t <= -threshold_10m):
        return 0, 0.0
    conf = compute_confidence(
        timeframes, bias, threshold_1h, threshold_30m, threshold_10m
    )
    return bias, conf


def slim_timeframes(ctx: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """Payload-sized TF metrics."""
    out: dict[str, dict[str, float]] = {}
    for k, v in ctx.items():
        out[k] = {
            "mf_delta_norm": round(float(v["mf_delta_norm"]), 4),
            "retail_delta_norm": round(float(v["retail_delta_norm"]), 4),
            "mf_delta": round(float(v["mf_delta"]), 2),
        }
    return out


def build_payload(
    timestamp: str,
    symbol: str,
    price: float,
    timeframes: dict[str, dict[str, float]],
    composite_signal: int,
    confidence_score: float,
) -> dict[str, Any]:
    div, div_msg = detect_divergence(timeframes)
    return {
        "timestamp": timestamp,
        "symbol": symbol,
        "price": round(float(price), 2),
        "timeframes": slim_timeframes(timeframes),
        "composite_signal": int(composite_signal),
        "confidence_score": round(float(confidence_score), 4),
        "divergence_detected": bool(div),
        "divergence_message": div_msg,
    }


def active_session(ts: pd.Timestamp, sessions: dict[str, tuple[str, str]]) -> str:
    """
    Resolve trading session in US/Eastern.

    Asian wraps midnight: 18:00 → 01:00 ET.
    """
    et = ts.tz_convert("America/New_York") if ts.tzinfo else ts.tz_localize("UTC").tz_convert("America/New_York")
    minutes = et.hour * 60 + et.minute

    def to_min(hhmm: str) -> int:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)

    for name, (start, end) in sessions.items():
        s, e = to_min(start), to_min(end)
        if s < e:
            if s <= minutes < e:
                return name
        else:
            # wraps midnight
            if minutes >= s or minutes < e:
                return name
    return "off_hours"
