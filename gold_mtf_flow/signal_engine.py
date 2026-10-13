"""Multi-timeframe alignment and composite signal generation."""

from __future__ import annotations

from typing import Any

import numpy as np


def _bias_1h(mf_norm_1h: float, threshold_1h: float) -> int:
    """Return +1 bullish, -1 bearish, 0 neutral."""
    if mf_norm_1h > threshold_1h:
        return 1
    if mf_norm_1h < -threshold_1h:
        return -1
    return 0


def _confirms_30m(mf_norm_30m: float, bias: int, threshold_30m: float) -> bool:
    """30m MF delta aligns with 1H bias."""
    if bias == 0:
        return False
    if bias == 1:
        return mf_norm_30m > threshold_30m
    return mf_norm_30m < -threshold_30m


def _trigger_10m(mf_norm_10m: float, bias: int, threshold_10m: float) -> bool:
    """10m shows strong MF shift in direction of higher-TF bias."""
    if bias == 1:
        return mf_norm_10m >= threshold_10m
    if bias == -1:
        return mf_norm_10m <= -threshold_10m
    return False


def compute_confidence(
    timeframes: dict[str, dict[str, float]],
    composite_signal: int,
    threshold_1h: float,
    threshold_30m: float,
    threshold_10m: float,
) -> float:
    """
    Heuristic confidence in [0, 1] from alignment strength and magnitude.

    Penalizes retail vs MF divergence on 30m/1H when signal is directional.
    """
    if composite_signal == 0:
        return 0.0

    h = timeframes["1H"]["mf_delta_norm"]
    m = timeframes["30m"]["mf_delta_norm"]
    t = timeframes["10m"]["mf_delta_norm"]
    sign = float(composite_signal)

    mag = (
        min(abs(h) / max(threshold_1h, 1e-6), 1.5)
        + min(abs(m) / max(threshold_30m, 1e-6), 1.5)
        + min(abs(t) / max(threshold_10m, 1e-6), 1.5)
    ) / 4.5

    align = 1.0 if np.sign(h) == np.sign(m) == np.sign(t) == sign else 0.6

    div_penalty = 1.0
    for key in ("30m", "1H"):
        mf_n = timeframes[key]["mf_delta_norm"]
        rt_n = timeframes[key]["retail_delta_norm"]
        if sign > 0 and rt_n > 0.2 and mf_n < sign * threshold_1h:
            div_penalty *= 0.85
        if sign < 0 and rt_n < -0.2 and mf_n > sign * threshold_1h:
            div_penalty *= 0.85

    return float(np.clip(mag * align * div_penalty, 0.0, 1.0))


def composite_signal_from_context(
    timeframes: dict[str, dict[str, float]],
    threshold_1h: float = 0.15,
    threshold_30m: float = 0.20,
    threshold_10m: float = 0.30,
) -> tuple[int, float]:
    """
    Generate composite signal and confidence from MTF metrics.

    Returns:
        (signal, confidence) where signal in {-1, 0, 1}.
    """
    mf_1h = timeframes["1H"]["mf_delta_norm"]
    mf_30m = timeframes["30m"]["mf_delta_norm"]
    mf_10m = timeframes["10m"]["mf_delta_norm"]

    bias = _bias_1h(mf_1h, threshold_1h)
    if bias == 0:
        return 0, 0.0
    if not _confirms_30m(mf_30m, bias, threshold_30m):
        return 0, 0.0
    if not _trigger_10m(mf_10m, bias, threshold_10m):
        return 0, 0.0

    signal = bias
    confidence = compute_confidence(
        timeframes,
        signal,
        threshold_1h,
        threshold_30m,
        threshold_10m,
    )
    return signal, confidence


def build_payload(
    timestamp: str,
    symbol: str,
    timeframes: dict[str, dict[str, float]],
    composite_signal: int,
    confidence_score: float,
) -> dict[str, Any]:
    """JSON-serializable message for ZeroMQ."""
    return {
        "timestamp": timestamp,
        "symbol": symbol,
        "timeframes": timeframes,
        "composite_signal": composite_signal,
        "confidence_score": round(confidence_score, 4),
    }
