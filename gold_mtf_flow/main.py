"""Entry point: CSV replay, synthetic demo, or live tick stream hook."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

from gold_mtf_flow.config import apply_contract_defaults
from gold_mtf_flow.mtf_aggregator import TIMEFRAMES, build_all_timeframes, get_context_at_time
from gold_mtf_flow.signal_engine import build_payload, composite_signal_from_context
from gold_mtf_flow.tick_processor import prepare_ticks
from gold_mtf_flow.zmq_publisher import FlowPublisher


def _generate_demo_ticks(hours: float = 48.0, seed: int = 42) -> pd.DataFrame:
    """Synthetic tick stream for local testing without a CSV."""
    import numpy as np

    rng = np.random.default_rng(seed)
    n = int(hours * 3600 * 2)
    start = pd.Timestamp("2026-10-10T00:00:00Z")
    ts = start + pd.to_timedelta(rng.integers(0, int(hours * 3600 * 1e9), n), unit="ns")
    ts = pd.Series(ts).sort_values().reset_index(drop=True)
    price = 2650.0 + np.cumsum(rng.normal(0, 0.05, len(ts)))
    spread = 0.1
    bid = price - spread / 2
    ask = price + spread / 2
    volume = rng.integers(1, 40, len(ts)).astype(int)
    large_mask = rng.random(len(ts)) > 0.92
    volume[large_mask] = rng.integers(50, 200, large_mask.sum())
    return pd.DataFrame(
        {
            "timestamp": ts,
            "price": price,
            "volume": volume,
            "bid": bid,
            "ask": ask,
        }
    )


def process_and_publish(
    ticks: pd.DataFrame,
    cfg: dict,
    publisher: FlowPublisher | None = None,
    publish_on_10m_close_only: bool = True,
) -> list[dict]:
    """
    Process full tick history; emit payloads at each 10m bar close.

    Returns list of payloads (also published if ``publisher`` is set).
    """
    prepared = prepare_ticks(
        ticks,
        fixed_volume_threshold=float(cfg["fixed_volume_threshold"]),
        dynamic_percentile=float(cfg["dynamic_percentile"]),
        rolling_window_hours=float(cfg["rolling_window_hours"]),
    )
    all_bars = build_all_timeframes(prepared)
    bars_10 = all_bars["10m"]
    if bars_10.empty:
        return []

    payloads: list[dict] = []
    for ts_open in bars_10.index:
        ts_close = ts_open + pd.Timedelta(TIMEFRAMES["10m"])
        ctx = get_context_at_time(all_bars, ts_close)
        if ctx is None:
            continue

        signal, confidence = composite_signal_from_context(
            ctx,
            threshold_1h=float(cfg["threshold_1h"]),
            threshold_30m=float(cfg["threshold_30m"]),
            threshold_10m=float(cfg["threshold_10m"]),
        )
        payload = build_payload(
            timestamp=ts_close.strftime("%Y-%m-%dT%H:%M:%SZ"),
            symbol=str(cfg["symbol"]),
            timeframes=ctx,
            composite_signal=signal,
            confidence_score=confidence,
        )
        payloads.append(payload)
        if publisher is not None:
            publisher.publish(payload)

    return payloads


def main() -> None:
    parser = argparse.ArgumentParser(description="Gold MTF Main Force Flow publisher")
    parser.add_argument("--csv", type=Path, default=None, help="Tick CSV path")
    parser.add_argument("--demo", action="store_true", help="Run with synthetic ticks")
    parser.add_argument("--no-zmq", action="store_true", help="Skip ZeroMQ; print last payload")
    parser.add_argument("--replay-delay", type=float, default=0.0, help="Seconds between publishes")
    args = parser.parse_args()

    cfg = apply_contract_defaults()

    if args.csv:
        ticks = pd.read_csv(args.csv)
    elif args.demo:
        ticks = _generate_demo_ticks()
    else:
        parser.error("Provide --csv or --demo")

    publisher: FlowPublisher | None = None
    if not args.no_zmq:
        publisher = FlowPublisher(host=str(cfg["zmq_host"]), port=int(cfg["zmq_port"]))
        print(f"ZMQ PUB bound at {publisher.endpoint}")

    if args.replay_delay > 0 and publisher is not None:
        prepared = prepare_ticks(
            ticks,
            fixed_volume_threshold=float(cfg["fixed_volume_threshold"]),
            dynamic_percentile=float(cfg["dynamic_percentile"]),
            rolling_window_hours=float(cfg["rolling_window_hours"]),
        )
        all_bars = build_all_timeframes(prepared)
        for ts_open in all_bars["10m"].index:
            ts_close = ts_open + pd.Timedelta(TIMEFRAMES["10m"])
            ctx = get_context_at_time(all_bars, ts_close)
            if ctx is None:
                continue
            signal, confidence = composite_signal_from_context(
                ctx,
                threshold_1h=float(cfg["threshold_1h"]),
                threshold_30m=float(cfg["threshold_30m"]),
                threshold_10m=float(cfg["threshold_10m"]),
            )
            payload = build_payload(
                timestamp=ts_close.strftime("%Y-%m-%dT%H:%M:%SZ"),
                symbol=str(cfg["symbol"]),
                timeframes=ctx,
                composite_signal=signal,
                confidence_score=confidence,
            )
            publisher.publish(payload)
            print(payload)
            time.sleep(args.replay_delay)
        if publisher:
            publisher.close()
        return

    payloads = process_and_publish(ticks, cfg, publisher=publisher)
    if payloads:
        print("Last payload:", payloads[-1])
    else:
        print("No 10m payloads generated (insufficient data).")
    if publisher:
        publisher.close()


if __name__ == "__main__":
    main()
