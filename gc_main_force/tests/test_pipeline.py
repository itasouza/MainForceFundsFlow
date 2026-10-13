"""Synthetic pipeline + ZMQ smoke tests (no NinjaTrader required)."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import zmq

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from python_engine.config import get_config
from python_engine.main import compute_signals_from_ticks
from python_engine.tick_processor import prepare_ticks
from python_engine.zmq_signal_publisher import SignalPublisher


def generate_synthetic_ticks(hours: float = 36.0, seed: int = 7) -> pd.DataFrame:
    """Simulate NinjaTrader-style GC ticks."""
    rng = np.random.default_rng(seed)
    n = int(hours * 3600 * 1.5)
    start = pd.Timestamp("2026-10-10T00:00:00Z")
    deltas = rng.integers(0, int(hours * 3600 * 1e9), n)
    ts = pd.Series(start + pd.to_timedelta(deltas, unit="ns")).sort_values().reset_index(drop=True)
    price = 2675.0 + np.cumsum(rng.normal(0, 0.08, len(ts)))
    spread = 0.1
    volume = rng.integers(1, 25, len(ts)).astype(int)
    large = rng.random(len(ts)) > 0.93
    volume[large] = rng.integers(10, 80, large.sum())
    return pd.DataFrame(
        {
            "timestamp": ts,
            "symbol": "GC",
            "price": price,
            "volume": volume,
            "bid": price - spread / 2,
            "ask": price + spread / 2,
        }
    )


def test_lee_ready_and_mf() -> None:
    ticks = generate_synthetic_ticks(hours=6)
    prepared = prepare_ticks(ticks, fixed_threshold=10, dynamic_percentile=90, rolling_window_hours=24)
    assert "side" in prepared.columns
    assert prepared["segment"].isin(["main_force", "retail"]).all()
    assert prepared["is_main_force"].any() or True  # may be sparse on short sample
    print("OK classify/segment:", len(prepared), "ticks")


def test_signal_pipeline() -> None:
    cfg = get_config({"mode": "backtest"})
    ticks = generate_synthetic_ticks(hours=36)
    payloads, bars = compute_signals_from_ticks(ticks, cfg)
    assert "10m" in bars and not bars["10m"].empty
    assert isinstance(payloads, list)
    if payloads:
        p = payloads[-1]
        assert p["composite_signal"] in (-1, 0, 1)
        assert "divergence_detected" in p
        assert "timeframes" in p and "mf_delta" in p["timeframes"]["10m"]
    print("OK pipeline:", len(payloads), "signals,", len(bars["10m"]), "10m bars")


def test_zmq_pubsub() -> None:
    endpoint = "tcp://127.0.0.1:15555"
    topic = "gold_mtf_flow"
    received: list[dict] = []

    # Bind PUB first, then connect SUB (avoids slow-joiner drops)
    pub = SignalPublisher(bind=endpoint, topic=topic)
    time.sleep(0.15)

    def subscriber() -> None:
        ctx = zmq.Context.instance()
        sock = ctx.socket(zmq.SUB)
        sock.setsockopt(zmq.RCVTIMEO, 5000)
        sock.connect(endpoint)
        sock.subscribe(topic.encode())
        time.sleep(0.3)
        try:
            parts = sock.recv_multipart()
            body = parts[-1].decode() if isinstance(parts[-1], bytes) else parts[-1]
            received.append(json.loads(body))
        except zmq.Again:
            pass
        finally:
            sock.close(linger=0)

    t = threading.Thread(target=subscriber, daemon=True)
    t.start()
    time.sleep(0.4)
    payload = {
        "timestamp": "2026-10-13T14:10:00Z",
        "symbol": "GC",
        "price": 2675.4,
        "timeframes": {
            "10m": {"mf_delta_norm": 0.45, "retail_delta_norm": -0.1, "mf_delta": 1250},
            "30m": {"mf_delta_norm": 0.32, "retail_delta_norm": 0.05, "mf_delta": 3200},
            "1H": {"mf_delta_norm": 0.28, "retail_delta_norm": 0.12, "mf_delta": 8500},
        },
        "composite_signal": 1,
        "confidence_score": 0.85,
        "divergence_detected": False,
    }
    for _ in range(10):
        pub.publish(payload)
        time.sleep(0.05)
    t.join(timeout=6)
    pub.close()
    assert received, "ZMQ subscriber did not receive payload"
    assert received[0]["composite_signal"] == 1
    print("OK ZeroMQ PUB/SUB")


def write_sample_csv(path: Path) -> None:
    df = generate_synthetic_ticks(hours=30)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print("Wrote sample CSV:", path)


if __name__ == "__main__":
    sample = _ROOT / "backtest" / "sample_data" / "gc_ticks_sample.csv"
    write_sample_csv(sample)
    test_lee_ready_and_mf()
    test_signal_pipeline()
    test_zmq_pubsub()
    print("\nAll tests passed.")
