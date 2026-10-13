"""Lee-Ready tick classification and Main Force volume segmentation."""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

Side = Literal["buyer_initiated", "seller_initiated", "unknown"]


def classify_lee_ready(
    df: pd.DataFrame,
    price_col: str = "price",
    bid_col: str = "bid",
    ask_col: str = "ask",
) -> pd.Series:
    """
    Classify each tick as buyer- or seller-initiated using Lee-Ready.

    Uses quote rule when bid/ask are valid; otherwise tick rule vs prior price.
    """
    price = df[price_col].astype(float)
    side = pd.Series("unknown", index=df.index, dtype="object")

    has_bid = bid_col in df.columns and ask_col in df.columns
    if has_bid:
        bid = pd.to_numeric(df[bid_col], errors="coerce")
        ask = pd.to_numeric(df[ask_col], errors="coerce")
        mid = (bid + ask) / 2.0
        valid = bid.notna() & ask.notna() & (ask >= bid)

        side.loc[valid & (price > mid)] = "buyer_initiated"
        side.loc[valid & (price < mid)] = "seller_initiated"
        at_mid = valid & (price == mid)
        if at_mid.any():
            prev = price.shift(1)
            side.loc[at_mid & (price > prev)] = "buyer_initiated"
            side.loc[at_mid & (price < prev)] = "seller_initiated"

    unresolved = side == "unknown"
    if unresolved.any():
        prev = price.shift(1)
        side.loc[unresolved & (price > prev)] = "buyer_initiated"
        side.loc[unresolved & (price < prev)] = "seller_initiated"
        side.loc[unresolved & (price == prev)] = side.shift(1).fillna("unknown")

    return side


def _rolling_percentile_threshold(
    volume: pd.Series,
    timestamps: pd.DatetimeIndex,
    window_hours: float,
    percentile: float,
) -> pd.Series:
    """Rolling percentile of tick volume over ``window_hours`` (time-based)."""
    if len(volume) == 0:
        return pd.Series(dtype=float)
    v = volume.astype(float)
    ts = pd.Series(v.values, index=timestamps)
    window = f"{int(window_hours * 3600)}s"
    return ts.rolling(window=window, min_periods=1).quantile(percentile / 100.0)


def segment_main_force(
    df: pd.DataFrame,
    side_col: str = "side",
    volume_col: str = "volume",
    timestamp_col: str = "timestamp",
    fixed_volume_threshold: float = 50.0,
    dynamic_percentile: float = 90.0,
    rolling_window_hours: float = 24.0,
) -> pd.DataFrame:
    """
    Label each tick as Main Force or Retail.

    Main Force if volume >= max(fixed threshold, rolling dynamic percentile).
    """
    out = df.copy()
    ts = pd.to_datetime(out[timestamp_col], utc=True)
    out[timestamp_col] = ts
    vol = pd.to_numeric(out[volume_col], errors="coerce").fillna(0.0)

    dyn = _rolling_percentile_threshold(
        vol, pd.DatetimeIndex(ts), rolling_window_hours, dynamic_percentile
    )
    dyn = dyn.reindex(out.index).fillna(0.0)
    threshold = np.maximum(fixed_volume_threshold, dyn.values)
    out["is_main_force"] = vol.values >= threshold
    out["segment"] = np.where(out["is_main_force"], "main_force", "retail")
    if side_col not in out.columns:
        out[side_col] = classify_lee_ready(out)
    return out


def prepare_ticks(
    df: pd.DataFrame,
    fixed_volume_threshold: float,
    dynamic_percentile: float,
    rolling_window_hours: float,
) -> pd.DataFrame:
    """
    Normalize columns, classify Lee-Ready, and segment volume.

    Expected columns: timestamp, price, volume; optional bid, ask.
    """
    required = {"timestamp", "price", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing tick columns: {missing}")

    ticks = df.copy()
    ticks["timestamp"] = pd.to_datetime(ticks["timestamp"], utc=True)
    ticks = ticks.sort_values("timestamp").reset_index(drop=True)
    ticks["side"] = classify_lee_ready(ticks)
    ticks = segment_main_force(
        ticks,
        fixed_volume_threshold=fixed_volume_threshold,
        dynamic_percentile=dynamic_percentile,
        rolling_window_hours=rolling_window_hours,
    )
    return ticks
