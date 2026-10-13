"""Lee-Ready classification and GC Main Force vs Retail segmentation."""

from __future__ import annotations

import numpy as np
import pandas as pd


def classify_lee_ready(df: pd.DataFrame) -> pd.Series:
    """
    Classify ticks as buyer_initiated / seller_initiated.

    Quote rule (preferred):
      price >= ask → buyer; price <= bid → seller; otherwise tick rule.
    Tick rule fallback: vs previous price; equal → last known direction.
    """
    price = df["price"].astype(float)
    side = pd.Series("unknown", index=df.index, dtype="object")

    bid = pd.to_numeric(df.get("bid"), errors="coerce") if "bid" in df.columns else None
    ask = pd.to_numeric(df.get("ask"), errors="coerce") if "ask" in df.columns else None

    if bid is not None and ask is not None:
        valid = bid.notna() & ask.notna() & (ask >= bid) & (bid > 0) & (ask > 0)
        side.loc[valid & (price >= ask)] = "buyer_initiated"
        side.loc[valid & (price <= bid)] = "seller_initiated"

    unresolved = side == "unknown"
    if unresolved.any():
        prev = price.shift(1)
        side.loc[unresolved & (price > prev)] = "buyer_initiated"
        side.loc[unresolved & (price < prev)] = "seller_initiated"
        # equal / first tick: propagate last known side
        equal_mask = unresolved & ((price == prev) | prev.isna())
        side.loc[equal_mask] = side.shift(1).fillna("unknown")
        # remaining first ticks → mark as buyer by convention
        still = side == "unknown"
        side.loc[still] = "buyer_initiated"

    return side


def _rolling_percentile(
    volume: pd.Series,
    timestamps: pd.DatetimeIndex,
    window_hours: float,
    percentile: float,
) -> pd.Series:
    """Time-based rolling percentile of tick volumes."""
    if len(volume) == 0:
        return pd.Series(dtype=float)
    series = pd.Series(volume.astype(float).values, index=timestamps)
    window = f"{int(window_hours * 3600)}s"
    return series.rolling(window=window, min_periods=1).quantile(percentile / 100.0)


def segment_main_force(
    df: pd.DataFrame,
    fixed_threshold: float = 10.0,
    dynamic_percentile: float = 90.0,
    rolling_window_hours: float = 24.0,
) -> pd.DataFrame:
    """
    Label Main Force for GC: volume >= fixed AND >= rolling percentile.

    Retail = all other trades.
    """
    out = df.copy().reset_index(drop=True)
    ts = pd.to_datetime(out["timestamp"], utc=True)
    out["timestamp"] = ts
    vol = pd.to_numeric(out["volume"], errors="coerce").fillna(0.0)

    # Rolling on a time index; duplicate timestamps are common in live ticks.
    # Compute on a uniquely ordered view, then map values back by position.
    ordered = pd.DataFrame({"volume": vol.astype(float).values}, index=pd.DatetimeIndex(ts))
    ordered = ordered.sort_index()
    # Keep original row order via a stable positional key
    ordered["_pos"] = range(len(ordered))
    window = f"{int(rolling_window_hours * 3600)}s"
    ordered["_dyn"] = (
        ordered["volume"]
        .rolling(window=window, min_periods=1)
        .quantile(dynamic_percentile / 100.0)
    )
    dyn = (
        ordered.sort_values("_pos")["_dyn"]
        .to_numpy(dtype=float, copy=False)
    )
    dyn = pd.Series(dyn, index=out.index).fillna(0.0)
    # AND rule for GC institutional filter
    out["is_main_force"] = (vol.values >= fixed_threshold) & (vol.values >= dyn.to_numpy())
    out["segment"] = np.where(out["is_main_force"], "main_force", "retail")
    return out


def prepare_ticks(
    df: pd.DataFrame,
    fixed_threshold: float = 10.0,
    dynamic_percentile: float = 90.0,
    rolling_window_hours: float = 24.0,
) -> pd.DataFrame:
    """Normalize, classify Lee-Ready, and segment Main Force / Retail."""
    required = {"timestamp", "price", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing tick columns: {missing}")

    ticks = df.copy()
    ticks["timestamp"] = pd.to_datetime(ticks["timestamp"], utc=True)
    ticks = ticks.sort_values("timestamp").reset_index(drop=True)
    ticks = ticks.loc[ticks["volume"].astype(float) > 0].reset_index(drop=True)
    ticks["side"] = classify_lee_ready(ticks)
    ticks = segment_main_force(
        ticks,
        fixed_threshold=fixed_threshold,
        dynamic_percentile=dynamic_percentile,
        rolling_window_hours=rolling_window_hours,
    )
    return ticks
