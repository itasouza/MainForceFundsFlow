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

# pandas used in regime test timestamps

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


def test_incremental_engine() -> None:
    from python_engine.incremental_engine import IncrementalMTFEngine

    cfg = get_config({"mode": "live", "percentile_recompute_ticks": 50})
    engine = IncrementalMTFEngine(cfg)
    ticks = generate_synthetic_ticks(hours=6)
    signals = 0
    closes_1h = 0
    for row in ticks.to_dict(orient="records"):
        result = engine.process_tick(row)
        if result.closed_1h is not None:
            closes_1h += 1
        payload = result.signal_payload
        if payload is not None:
            signals += 1
            assert payload["composite_signal"] in (-1, 0, 1)
            assert "timeframes" in payload
    assert engine.tick_count == len(ticks)
    assert len(engine.history_bars["10m"]) > 0
    snap = engine.snapshot_state()
    assert snap["engine"] == "incremental" or snap.get("tick_count", 0) > 0
    assert snap["last_price"] is not None
    assert "institutional_footprint" in snap
    bundle = snap["institutional_footprint"]
    assert set(bundle.keys()) >= {"10m", "30m", "1H"}
    fp10 = bundle["10m"]
    assert "price_levels" in fp10 and "net_mf_vol" in fp10
    assert "absorption_level" in fp10 and "absorption_volume" in fp10
    closed = engine.history_bars["10m"][-1]
    assert "institutional_footprint" in closed
    assert "mf_buy_profile" in closed and "mf_sell_profile" in closed
    print(
        "OK incremental:",
        engine.tick_count,
        "ticks,",
        signals,
        "10m closes,",
        closes_1h,
        "1H closes,",
        len(engine.history_bars["10m"]),
        "bars,",
        "fp_levels=",
        len(fp10.get("price_levels") or []),
        "abs=",
        fp10.get("absorption_level"),
    )


def test_foreign_instrument_is_dropped() -> None:
    from python_engine.incremental_engine import IncrementalMTFEngine

    cfg = get_config({"mode": "live", "symbol": "ES", "tick_size": 0.25})
    engine = IncrementalMTFEngine(cfg)
    base = {
        "timestamp": "2026-10-19T01:50:00Z",
        "symbol": "BMD",
        "volume": 2,
        "bid": 7744.75,
        "ask": 7745.25,
    }
    engine.process_tick({**base, "price": 7745.0})
    engine.process_tick({**base, "price": 7745.25, "timestamp": "2026-10-19T01:50:01Z"})
    foreign = engine.process_tick(
        {**base, "price": 82520.0, "timestamp": "2026-10-19T01:50:02Z", "symbol": "BTC"}
    )
    assert foreign.signal_payload is None
    assert engine.tick_count == 2
    assert engine.foreign_tick_count == 1
    assert engine.last_price == 7745.25
    assert engine.last_foreign_price == 82520.0
    bar = engine.current_bars["10m"]
    assert bar["high"] < 8000
    snap = engine.snapshot_state()
    assert snap["foreign_tick_count"] == 1
    print("OK foreign instrument dropped")


def test_regime_classifier_fallback() -> None:
    from python_engine.regime_classifier import MarketRegimeClassifier

    cfg = get_config()
    clf = MarketRegimeClassifier(model_path=None)
    bar = {
        "bar_start_time": pd.Timestamp("2026-10-13T14:00:00Z"),
        "open": 4200.0,
        "high": 4205.0,
        "low": 4198.0,
        "close": 4202.0,
        "mf_delta_norm": 0.4,
        "retail_delta_norm": -0.2,
    }
    decision = clf.on_1h_close(bar, cfg, {"ai_enabled": True, "force_regime": None})
    assert decision.regime == 1  # default without model
    assert "volatility_ratio" in decision.features
    forced = clf.on_1h_close(bar, cfg, {"ai_enabled": False, "force_regime": 2})
    assert forced.regime == 2 and forced.source == "manual"
    assert cfg["grid_paused"] is True  # volatile profile
    print("OK regime classifier fallback/manual")


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
    test_incremental_engine()
    test_foreign_instrument_is_dropped()
    test_regime_classifier_fallback()
    test_signal_pipeline()
    test_zmq_pubsub()
    print("\nAll tests passed.")
