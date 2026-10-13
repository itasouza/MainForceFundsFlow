"""Resample classified ticks to 10m, 30m, 1H bars with MF/retail deltas."""

from __future__ import annotations

import pandas as pd

TIMEFRAMES: dict[str, str] = {
    "10m": "10min",
    "30m": "30min",
    "1H": "1h",
}


def _ohlcv_from_ticks(ticks: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Build OHLCV bars from ticks for a pandas offset rule."""
    t = ticks.set_index("timestamp")
    price = t["price"].astype(float)
    vol = t["volume"].astype(float)
    ohlc = price.resample(rule, label="left", closed="left").ohlc()
    ohlc["volume"] = vol.resample(rule, label="left", closed="left").sum()
    ohlc = ohlc.dropna(subset=["open"])
    return ohlc


def _delta_norm_for_segment(
    ticks: pd.DataFrame,
    rule: str,
    segment: str,
) -> pd.DataFrame:
    """Sum buyer/seller volume for a segment within each bar; compute normalized delta."""
    if segment == "main_force":
        sub = ticks.loc[ticks["segment"] == "main_force"].copy()
        prefix = "mf"
    else:
        sub = ticks.loc[ticks["segment"] == "retail"].copy()
        prefix = "retail"

    idx = _ohlcv_from_ticks(ticks, rule).index
    if sub.empty:
        return pd.DataFrame(
            {
                f"{prefix}_buy_vol": 0.0,
                f"{prefix}_sell_vol": 0.0,
                f"{prefix}_delta": 0.0,
                f"{prefix}_delta_norm": 0.0,
            },
            index=idx,
        )

    sub = sub.set_index("timestamp")
    buy = sub.loc[sub["side"] == "buyer_initiated", "volume"].astype(float)
    sell = sub.loc[sub["side"] == "seller_initiated", "volume"].astype(float)

    buy_sum = buy.resample(rule, label="left", closed="left").sum()
    sell_sum = sell.resample(rule, label="left", closed="left").sum()

    bar_idx = idx.union(buy_sum.index).union(sell_sum.index).sort_values()
    buy_sum = buy_sum.reindex(bar_idx, fill_value=0.0)
    sell_sum = sell_sum.reindex(bar_idx, fill_value=0.0)
    delta = buy_sum - sell_sum
    denom = buy_sum + sell_sum + 1e-8
    delta_norm = delta / denom

    return pd.DataFrame(
        {
            f"{prefix}_buy_vol": buy_sum,
            f"{prefix}_sell_vol": sell_sum,
            f"{prefix}_delta": delta,
            f"{prefix}_delta_norm": delta_norm,
        },
        index=bar_idx,
    ).reindex(idx, fill_value=0.0)


def aggregate_timeframe(ticks: pd.DataFrame, tf_key: str) -> pd.DataFrame:
    """Full bar table for one timeframe key (10m, 30m, 1H)."""
    rule = TIMEFRAMES[tf_key]
    ohlc = _ohlcv_from_ticks(ticks, rule)
    mf = _delta_norm_for_segment(ticks, rule, "main_force")
    retail = _delta_norm_for_segment(ticks, rule, "retail")

    bars = ohlc.join(mf, how="left").join(retail, how="left")
    bars = bars.fillna(
        {
            "mf_buy_vol": 0.0,
            "mf_sell_vol": 0.0,
            "mf_delta": 0.0,
            "mf_delta_norm": 0.0,
            "retail_buy_vol": 0.0,
            "retail_sell_vol": 0.0,
            "retail_delta": 0.0,
            "retail_delta_norm": 0.0,
        }
    )
    bars["timeframe"] = tf_key
    return bars.sort_index()


def build_all_timeframes(ticks: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return dict of bar DataFrames keyed by 10m, 30m, 1H."""
    return {key: aggregate_timeframe(ticks, key) for key in TIMEFRAMES}


def bar_period(tf_key: str) -> pd.Timedelta:
    """Calendar period for a timeframe key."""
    return pd.Timedelta(TIMEFRAMES[tf_key])


def is_bar_closed(bar_open: pd.Timestamp, tf_key: str, as_of: pd.Timestamp) -> bool:
    """True if the bar starting at ``bar_open`` is fully closed at ``as_of``."""
    return as_of >= bar_open + bar_period(tf_key)


def get_context_at_time(
    all_bars: dict[str, pd.DataFrame],
    as_of: pd.Timestamp,
) -> dict[str, dict[str, float]] | None:
    """
    Snapshot mf/retail delta_norm for each TF using the latest *closed* bar.

    Returns None if 10m context is unavailable.
    """
    ctx: dict[str, dict[str, float]] = {}
    for tf_key, bars in all_bars.items():
        if bars.empty:
            return None
        period = bar_period(tf_key)
        closed = bars.index[bars.index + period <= as_of]
        if len(closed) == 0:
            return None
        row = bars.loc[closed[-1]]
        ctx[tf_key] = {
            "mf_delta_norm": float(row["mf_delta_norm"]),
            "retail_delta_norm": float(row["retail_delta_norm"]),
        }
    return ctx
