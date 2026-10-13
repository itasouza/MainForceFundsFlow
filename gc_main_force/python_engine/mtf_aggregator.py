"""Resample classified ticks to 10m / 30m / 1H bars with MF metrics."""

from __future__ import annotations

import pandas as pd

TIMEFRAMES: dict[str, str] = {
    "10m": "10min",
    "30m": "30min",
    "1H": "1h",
}


def _ohlcv(ticks: pd.DataFrame, rule: str) -> pd.DataFrame:
    t = ticks.set_index("timestamp")
    price = t["price"].astype(float)
    vol = t["volume"].astype(float)
    ohlc = price.resample(rule, label="left", closed="left").ohlc()
    ohlc["volume"] = vol.resample(rule, label="left", closed="left").sum()
    ohlc = ohlc.dropna(subset=["open"])
    if ohlc.empty:
        ohlc["price_change_pct"] = pd.Series(dtype=float)
    else:
        ohlc["price_change_pct"] = ohlc["close"].pct_change().fillna(0.0) * 100.0
    return ohlc


def _segment_deltas(ticks: pd.DataFrame, rule: str, segment: str) -> pd.DataFrame:
    prefix = "mf" if segment == "main_force" else "retail"
    idx = _ohlcv(ticks, rule).index
    sub = ticks.loc[ticks["segment"] == segment].copy()
    empty = pd.DataFrame(
        {
            f"{prefix}_buy_vol": 0.0,
            f"{prefix}_sell_vol": 0.0,
            f"{prefix}_delta": 0.0,
            f"{prefix}_delta_norm": 0.0,
        },
        index=idx,
    )
    if sub.empty or idx.empty:
        return empty

    sub = sub.set_index("timestamp")
    buy = sub.loc[sub["side"] == "buyer_initiated", "volume"].astype(float)
    sell = sub.loc[sub["side"] == "seller_initiated", "volume"].astype(float)
    buy_sum = buy.resample(rule, label="left", closed="left").sum()
    sell_sum = sell.resample(rule, label="left", closed="left").sum()
    bar_idx = idx.union(buy_sum.index).union(sell_sum.index).sort_values()
    buy_sum = buy_sum.reindex(bar_idx, fill_value=0.0)
    sell_sum = sell_sum.reindex(bar_idx, fill_value=0.0)
    delta = buy_sum - sell_sum
    delta_norm = delta / (buy_sum + sell_sum + 1e-8)
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
    """OHLCV + MF/retail deltas for one timeframe."""
    rule = TIMEFRAMES[tf_key]
    ohlc = _ohlcv(ticks, rule)
    mf = _segment_deltas(ticks, rule, "main_force")
    retail = _segment_deltas(ticks, rule, "retail")
    bars = ohlc.join(mf, how="left").join(retail, how="left")
    fill_cols = [
        "mf_buy_vol",
        "mf_sell_vol",
        "mf_delta",
        "mf_delta_norm",
        "retail_buy_vol",
        "retail_sell_vol",
        "retail_delta",
        "retail_delta_norm",
        "price_change_pct",
    ]
    bars = bars.fillna({c: 0.0 for c in fill_cols if c in bars.columns})
    # Trend vs previous bar MF delta_norm
    bars["mf_trend"] = bars["mf_delta_norm"].diff().fillna(0.0)
    bars["timeframe"] = tf_key
    return bars.sort_index()


def build_all_timeframes(ticks: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {key: aggregate_timeframe(ticks, key) for key in TIMEFRAMES}


def bar_period(tf_key: str) -> pd.Timedelta:
    return pd.Timedelta(TIMEFRAMES[tf_key])


def _empty_tf_metrics() -> dict[str, float]:
    return {
        "mf_delta_norm": 0.0,
        "retail_delta_norm": 0.0,
        "mf_delta": 0.0,
        "price_change_pct": 0.0,
        "prev_mf_delta_norm": float("nan"),
        "open": 0.0,
        "high": 0.0,
        "low": 0.0,
        "close": 0.0,
        "volume": 0.0,
    }


def get_context_at_time(
    all_bars: dict[str, pd.DataFrame],
    as_of: pd.Timestamp,
    require_all: bool = False,
) -> dict[str, dict[str, float]] | None:
    """
    Latest closed-bar metrics for each TF at ``as_of``.

    If ``require_all`` is False (live warmup), missing higher TFs are filled with zeros
    as long as at least one closed 10m bar exists.
    """
    ctx: dict[str, dict[str, float]] = {}
    for tf_key, bars in all_bars.items():
        if bars.empty:
            if require_all:
                return None
            ctx[tf_key] = _empty_tf_metrics()
            continue
        period = bar_period(tf_key)
        closed = bars.index[bars.index + period <= as_of]
        if len(closed) == 0:
            if require_all:
                return None
            ctx[tf_key] = _empty_tf_metrics()
            continue
        row = bars.loc[closed[-1]]
        prev_norm = float("nan")
        pos = bars.index.get_loc(closed[-1])
        if isinstance(pos, int) and pos > 0:
            prev_norm = float(bars.iloc[pos - 1]["mf_delta_norm"])
        ctx[tf_key] = {
            "mf_delta_norm": float(row["mf_delta_norm"]),
            "retail_delta_norm": float(row["retail_delta_norm"]),
            "mf_delta": float(row["mf_delta"]),
            "price_change_pct": float(row.get("price_change_pct", 0.0)),
            "prev_mf_delta_norm": prev_norm,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
    # Need a real 10m close to publish anything useful
    if ctx.get("10m", {}).get("volume", 0) == 0 and ctx.get("10m", {}).get("close", 0) == 0:
        return None
    return ctx
