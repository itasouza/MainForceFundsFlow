"""Backtest runner with simple performance metrics for GC MTF signals."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from python_engine.config import get_config
from python_engine.main import compute_signals_from_ticks
from python_engine.tick_receiver import load_ticks_csv


def evaluate(payloads: list[dict], bars_10: pd.DataFrame) -> pd.DataFrame:
    """Join signals to forward 10m returns."""
    if bars_10.empty or not payloads:
        return pd.DataFrame()
    closes = bars_10["close"]
    # Map signal timestamp (bar close) → previous bar open label
    records = []
    for p in payloads:
        ts_close = pd.Timestamp(p["timestamp"])
        if ts_close.tzinfo is None:
            ts_close = ts_close.tz_localize("UTC")
        # bar open = close - 10m
        ts_open = ts_close - pd.Timedelta("10min")
        if ts_open not in closes.index:
            # nearest prior
            prior = closes.index[closes.index <= ts_open]
            if len(prior) == 0:
                continue
            ts_open = prior[-1]
        pos = closes.index.get_loc(ts_open)
        if not isinstance(pos, int) or pos + 1 >= len(closes):
            continue
        c0 = float(closes.iloc[pos])
        c1 = float(closes.iloc[pos + 1])
        ret = (c1 - c0) / c0 if c0 else 0.0
        sig = int(p["composite_signal"])
        records.append(
            {
                "timestamp": p["timestamp"],
                "signal": sig,
                "confidence": p["confidence_score"],
                "fwd_ret_10m": ret,
                "aligned_pnl": sig * ret,
                "divergence": p.get("divergence_detected", False),
            }
        )
    return pd.DataFrame(records)


def summarize(df: pd.DataFrame) -> None:
    if df.empty:
        print("Sem resultados.")
        return
    for sig in (-1, 0, 1):
        sub = df.loc[df["signal"] == sig]
        if sub.empty:
            continue
        hit = (sub["aligned_pnl"] > 0).mean() if sig != 0 else float("nan")
        print(
            f"signal={sig:+d} n={len(sub)} "
            f"mean_aligned={sub['aligned_pnl'].mean():.6f} "
            f"hit_rate={hit:.2%}" if sig != 0 else f"signal={sig:+d} n={len(sub)}"
        )
    directional = df.loc[df["signal"] != 0]
    if not directional.empty:
        print(f"Total directional mean aligned PnL: {directional['aligned_pnl'].mean():.6f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="GC Main Force backtest")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    cfg = get_config({"mode": "backtest"})
    ticks = load_ticks_csv(args.csv)
    payloads, all_bars = compute_signals_from_ticks(ticks, cfg)
    results = evaluate(payloads, all_bars["10m"])
    summarize(results)
    if args.output:
        results.to_csv(args.output, index=False)
        print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
