"""Evaluate composite signals vs forward 10m/30m returns."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from gold_mtf_flow.config import apply_contract_defaults
from gold_mtf_flow.mtf_aggregator import TIMEFRAMES, build_all_timeframes
from gold_mtf_flow.signal_engine import composite_signal_from_context
from gold_mtf_flow.tick_processor import prepare_ticks


def load_ticks_csv(path: Path) -> pd.DataFrame:
    """Load ticks from CSV with timestamp, price, volume; optional bid, ask."""
    df = pd.read_csv(path)
    return df


def run_backtest(ticks: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    Walk 10m bar closes; record signal and forward returns on 10m and 30m bars.
    """
    prepared = prepare_ticks(
        ticks,
        fixed_volume_threshold=float(cfg["fixed_volume_threshold"]),
        dynamic_percentile=float(cfg["dynamic_percentile"]),
        rolling_window_hours=float(cfg["rolling_window_hours"]),
    )
    all_bars = build_all_timeframes(prepared)
    bars_10 = all_bars["10m"]
    if len(bars_10) < 3:
        return pd.DataFrame()

    records: list[dict] = []
    for i, ts_open in enumerate(bars_10.index[:-1]):
        ts_close = ts_open + pd.Timedelta(TIMEFRAMES["10m"])
        ctx: dict[str, dict[str, float]] = {}
        ok = True
        for tf_key, bars in all_bars.items():
            period = pd.Timedelta(TIMEFRAMES[tf_key])
            closed = bars.index[bars.index + period <= ts_close]
            if len(closed) == 0:
                ok = False
                break
            row = bars.loc[closed[-1]]
            ctx[tf_key] = {
                "mf_delta_norm": float(row["mf_delta_norm"]),
                "retail_delta_norm": float(row["retail_delta_norm"]),
            }
        if not ok:
            continue

        signal, conf = composite_signal_from_context(
            ctx,
            threshold_1h=float(cfg["threshold_1h"]),
            threshold_30m=float(cfg["threshold_30m"]),
            threshold_10m=float(cfg["threshold_10m"]),
        )

        close_now = float(bars_10.loc[ts_open, "close"])
        # Forward 10m return from this bar close
        if i + 1 < len(bars_10):
            close_10_fwd = float(bars_10.iloc[i + 1]["close"])
            ret_10m = (close_10_fwd - close_now) / close_now if close_now else 0.0
        else:
            ret_10m = np.nan

        # Forward 30m: find 30m bar that closes after ts_close
        bars_30 = all_bars["30m"]
        period_30 = pd.Timedelta(TIMEFRAMES["30m"])
        closed_30 = bars_30.index[bars_30.index + period_30 <= ts_close]
        ret_30m = np.nan
        if len(closed_30) > 0:
            label_30 = closed_30[-1]
            pos = bars_30.index.get_loc(label_30)
            if isinstance(pos, int) and pos + 1 < len(bars_30):
                c0 = float(bars_30.iloc[pos]["close"])
                c1 = float(bars_30.iloc[pos + 1]["close"])
                ret_30m = (c1 - c0) / c0 if c0 else 0.0

        records.append(
            {
                "timestamp": ts_close.isoformat(),
                "composite_signal": signal,
                "confidence_score": conf,
                "mf_delta_norm_10m": ctx["10m"]["mf_delta_norm"],
                "ret_forward_10m": ret_10m,
                "ret_forward_30m": ret_30m,
            }
        )

    return pd.DataFrame(records)


def summarize(results: pd.DataFrame) -> None:
    """Print simple hit-rate stats by signal direction."""
    if results.empty:
        print("No results.")
        return
    for sig in (-1, 0, 1):
        sub = results.loc[results["composite_signal"] == sig]
        if sub.empty:
            continue
        aligned_10 = (sub["composite_signal"] * sub["ret_forward_10m"]).mean()
        aligned_30 = (sub["composite_signal"] * sub["ret_forward_30m"]).mean()
        print(
            f"signal={sig:+d} n={len(sub)} "
            f"mean(sig*ret_10m)={aligned_10:.6f} mean(sig*ret_30m)={aligned_30:.6f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest MTF Main Force signals")
    parser.add_argument("csv", type=Path, help="Path to tick CSV")
    parser.add_argument("--output", type=Path, default=None, help="Optional results CSV")
    args = parser.parse_args()

    cfg = apply_contract_defaults()
    ticks = load_ticks_csv(args.csv)
    results = run_backtest(ticks, cfg)
    summarize(results)
    if args.output:
        results.to_csv(args.output, index=False)
        print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
