"""Orchestrate tick ingest → MTF flow → signal publish → shared state."""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

import pandas as pd

# Allow running as `python main.py` from python_engine/
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from python_engine.config import get_config
from python_engine.incremental_engine import IncrementalMTFEngine
from python_engine.mtf_aggregator import TIMEFRAMES, build_all_timeframes, get_context_at_time
from python_engine.signal_engine import (
    active_session,
    build_payload,
    composite_signal_from_context,
)
from python_engine.state_store import EngineStateStore
from python_engine.tick_processor import prepare_ticks
from python_engine.tick_receiver import NtTickSubscriber, TickBuffer, load_ticks_csv, run_live_loop
from python_engine.zmq_signal_publisher import SignalPublisher


def compute_signals_from_ticks(ticks: pd.DataFrame, cfg: dict) -> tuple[list[dict], dict]:
    """Full recompute; return payloads at each 10m close + latest bars dict."""
    prepared = prepare_ticks(
        ticks,
        fixed_threshold=float(cfg["mf_fixed_threshold_contracts"]),
        dynamic_percentile=float(cfg["mf_dynamic_percentile"]),
        rolling_window_hours=float(cfg["rolling_window_hours"]),
    )
    all_bars = build_all_timeframes(prepared)
    bars_10 = all_bars["10m"]
    payloads: list[dict] = []
    if bars_10.empty:
        return payloads, all_bars

    for ts_open in bars_10.index:
        ts_close = ts_open + pd.Timedelta(TIMEFRAMES["10m"])
        ctx = get_context_at_time(all_bars, ts_close, require_all=False)
        if ctx is None:
            continue
        signal, conf = composite_signal_from_context(
            ctx,
            threshold_1h=float(cfg["threshold_1h"]),
            threshold_30m=float(cfg["threshold_30m"]),
            threshold_10m=float(cfg["threshold_10m"]),
        )
        price = float(ctx["10m"]["close"])
        payload = build_payload(
            timestamp=ts_close.strftime("%Y-%m-%dT%H:%M:%SZ"),
            symbol=str(cfg["symbol"]),
            price=price,
            timeframes=ctx,
            composite_signal=signal,
            confidence_score=conf,
        )
        payload["session"] = active_session(ts_close, cfg["sessions"])
        payloads.append(payload)
    return payloads, all_bars


def _engine_recompute(
    ticks: pd.DataFrame,
    cfg: dict,
    store: EngineStateStore,
    publisher: SignalPublisher | None,
    published_keys: set[str],
) -> None:
    if ticks.empty:
        return

    price = float(ticks["price"].iloc[-1])
    open_px = store.state.get("session_open_price")
    if open_px is None:
        open_px = float(ticks["price"].iloc[0])
    ts_last = pd.Timestamp(ticks["timestamp"].iloc[-1])
    store.update(
        last_price=price,
        session_open_price=open_px,
        active_session=active_session(ts_last, cfg["sessions"]),
        tick_count=len(ticks),
    )

    if len(ticks) < 10:
        return

    try:
        payloads, all_bars = compute_signals_from_ticks(ticks, cfg)
    except Exception as exc:  # noqa: BLE001 — keep live loop alive
        print(f"recompute error: {exc}")
        return

    store.set_bars_10m(all_bars["10m"], limit=int(cfg["chart_bars_display"]))
    if not payloads:
        # Warmup: still expose a neutral snapshot from latest closed bars if any
        bars_10 = all_bars.get("10m")
        if bars_10 is not None and not bars_10.empty:
            ts_close = bars_10.index[-1] + pd.Timedelta(TIMEFRAMES["10m"])
            ctx = get_context_at_time(all_bars, ts_close, require_all=False)
            if ctx is not None:
                signal, conf = composite_signal_from_context(
                    ctx,
                    threshold_1h=float(cfg["threshold_1h"]),
                    threshold_30m=float(cfg["threshold_30m"]),
                    threshold_10m=float(cfg["threshold_10m"]),
                )
                snap = build_payload(
                    timestamp=ts_close.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    symbol=str(cfg["symbol"]),
                    price=float(ctx["10m"]["close"] or price),
                    timeframes=ctx,
                    composite_signal=signal,
                    confidence_score=conf,
                )
                snap["session"] = active_session(ts_close, cfg["sessions"])
                store.push_signal(snap)
        return

    last = payloads[-1]
    for p in payloads:
        key = p["timestamp"]
        if key in published_keys:
            continue
        published_keys.add(key)
        store.push_signal(p)
        if publisher is not None:
            publisher.publish(p)
    store.push_signal(last)
    store.update(last_price=price, latest_signal=last)


def run_live_incremental(cfg: dict, store: EngineStateStore) -> None:
    """High-performance live path: O(1) per tick; disk write ONLY on 10m bar close."""
    transport = str(cfg.get("nt_tick_transport", "zmq"))
    sub = NtTickSubscriber(
        endpoint=str(cfg["nt_zmq_subscribe"]),
        topic=str(cfg["nt_zmq_topic"]),
        transport=transport,
    )
    publisher = SignalPublisher(
        bind=str(cfg["signal_zmq_publish"]),
        topic=str(cfg["signal_zmq_topic"]),
    )
    engine = IncrementalMTFEngine(cfg)
    stop = threading.Event()

    # One-time boot write so dashboard sees mode=live before first 10m close
    store.update(mode="live", live=False, tick_count=0, engine="incremental", persist=True)
    print(f"Listening ticks (incremental/{transport}): {cfg['nt_zmq_subscribe']} topic={cfg['nt_zmq_topic']}")
    print(f"Publishing signals: {cfg['signal_zmq_publish']} topic={cfg['signal_zmq_topic']}")
    print("Disk write: signal_state.json ONLY on 10m bar close (avoids Windows file locks).")

    t = threading.Thread(
        target=_incremental_recv_loop,
        args=(sub, engine, store, publisher, stop),
        daemon=True,
    )
    t.start()
    try:
        while not stop.is_set():
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopping live engine…")
    finally:
        stop.set()
        sub.close()
        publisher.close()


def _incremental_recv_loop(
    sub: NtTickSubscriber,
    engine: IncrementalMTFEngine,
    store: EngineStateStore,
    publisher: SignalPublisher,
    stop: threading.Event,
) -> None:
    last_tick_mono = 0.0
    while not stop.is_set():
        tick = sub.recv_tick()
        if tick is None:
            if last_tick_mono and (time.monotonic() - last_tick_mono) > 5.0:
                store.update(persist=False, live=False)
            continue
        if tick["volume"] <= 0:
            continue

        last_tick_mono = time.monotonic()
        payload = engine.process_tick(tick)
        snap = engine.snapshot_state()

        if payload is not None:
            # ONLY disk persistence point in the live loop
            store.push_signal(payload, persist=False)
            store.merge(snap, persist=True)
            try:
                publisher.publish(payload)
            except Exception as exc:  # noqa: BLE001
                print(f"ZMQ publish error: {exc}")
            print(
                f"10m close signal={payload['composite_signal']} "
                f"conf={payload['confidence_score']} ts={payload['timestamp']}"
            )
            continue

        # In-memory only between bar closes (no JSON write → no PermissionError)
        store.merge(snap, persist=False)


def run_live_batch(cfg: dict, store: EngineStateStore) -> None:
    """Legacy full-recompute live path (kept for comparison / debugging)."""
    buffer = TickBuffer(max_hours=float(cfg["tick_buffer_hours"]))
    transport = str(cfg.get("nt_tick_transport", "zmq"))
    sub = NtTickSubscriber(
        endpoint=str(cfg["nt_zmq_subscribe"]),
        topic=str(cfg["nt_zmq_topic"]),
        transport=transport,
    )
    publisher = SignalPublisher(
        bind=str(cfg["signal_zmq_publish"]),
        topic=str(cfg["signal_zmq_topic"]),
    )
    stop = threading.Event()
    published: set[str] = set()

    store.update(mode="live", live=False, tick_count=0, engine="batch")
    print(f"Listening ticks (batch/{transport}): {cfg['nt_zmq_subscribe']} topic={cfg['nt_zmq_topic']}")
    print(f"Publishing signals: {cfg['signal_zmq_publish']} topic={cfg['signal_zmq_topic']}")

    t = threading.Thread(
        target=run_live_loop,
        args=(sub, buffer, stop),
        daemon=True,
    )
    t.start()

    every = int(cfg["recompute_every_ticks"])
    last_count = 0
    try:
        while True:
            time.sleep(0.5)
            age = buffer.age_sec()
            live = age is not None and age < 5.0
            store.update(live=live, tick_count=buffer.count)
            if buffer.count == last_count:
                continue
            if buffer.count - last_count < every and last_count > 0:
                if age is not None and age < 2.0 and (buffer.count % every != 0):
                    continue
            last_count = buffer.count
            df = buffer.to_dataframe()
            _engine_recompute(df, cfg, store, publisher, published)
    except KeyboardInterrupt:
        print("\nStopping live engine…")
    finally:
        stop.set()
        sub.close()
        publisher.close()


def run_live(cfg: dict, store: EngineStateStore) -> None:
    if str(cfg.get("live_engine", "incremental")).lower() == "batch":
        run_live_batch(cfg, store)
    else:
        run_live_incremental(cfg, store)


def run_backtest(cfg: dict, store: EngineStateStore, csv_path: Path, publish: bool) -> None:
    ticks = load_ticks_csv(csv_path)
    store.update(mode="backtest", live=False, tick_count=len(ticks), session_open_price=float(ticks["price"].iloc[0]))
    publisher = None
    if publish:
        publisher = SignalPublisher(
            bind=str(cfg["signal_zmq_publish"]),
            topic=str(cfg["signal_zmq_topic"]),
        )
    published: set[str] = set()
    payloads, all_bars = compute_signals_from_ticks(ticks, cfg)
    store.set_bars_10m(all_bars["10m"], limit=int(cfg["chart_bars_display"]))
    for p in payloads:
        published.add(p["timestamp"])
        store.push_signal(p)
        if publisher is not None:
            publisher.publish(p)
    if payloads:
        store.update(
            last_price=float(ticks["price"].iloc[-1]),
            latest_signal=payloads[-1],
            active_session=payloads[-1].get("session"),
        )
        print(f"Backtest done: {len(payloads)} signal events. Last={payloads[-1]}")
    else:
        print("Backtest produced no 10m signals (need more data).")
    if publisher is not None:
        publisher.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="GC Main Force Flow engine")
    parser.add_argument("--mode", choices=["live", "backtest"], default=None)
    parser.add_argument("--csv", type=Path, default=None, help="CSV for backtest mode")
    parser.add_argument("--publish", action="store_true", help="Publish ZMQ signals in backtest")
    parser.add_argument("--state-file", type=Path, default=None)
    args = parser.parse_args()

    cfg = get_config()
    if args.mode:
        cfg["mode"] = args.mode
    state_path = args.state_file or Path(__file__).resolve().parents[1] / cfg["state_file"]
    store = EngineStateStore(state_path)

    if cfg["mode"] == "live":
        run_live(cfg, store)
    else:
        if not args.csv:
            parser.error("--csv is required in backtest mode")
        run_backtest(cfg, store, args.csv, publish=args.publish)


if __name__ == "__main__":
    main()
