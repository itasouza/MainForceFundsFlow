"""Tick ingest from NinjaTrader (TCP JSON lines) or CSV backtest."""

from __future__ import annotations

import json
import socket
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import urlparse

import pandas as pd

REQUIRED_COLS = ("timestamp", "price", "volume")


def normalize_tick(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a tick dict to engine schema."""
    ts = pd.Timestamp(raw["timestamp"])
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return {
        "timestamp": ts,
        "symbol": str(raw.get("symbol", "GC")),
        "price": float(raw["price"]),
        "volume": float(raw.get("volume", 0)),
        "bid": float(raw["bid"]) if raw.get("bid") not in (None, "") else float("nan"),
        "ask": float(raw["ask"]) if raw.get("ask") not in (None, "") else float("nan"),
    }


def load_ticks_csv(path: Path | str) -> pd.DataFrame:
    """Load tick CSV with columns timestamp, price, volume [, bid, ask]."""
    df = pd.read_csv(path)
    missing = set(REQUIRED_COLS) - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")
    for col in ("bid", "ask"):
        if col not in df.columns:
            df[col] = float("nan")
    if "symbol" not in df.columns:
        df["symbol"] = "GC"
    rows = [normalize_tick(r) for r in df.to_dict(orient="records")]
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


def _parse_tcp_endpoint(endpoint: str) -> tuple[str, int]:
    """Parse ``tcp://host:port`` into host/port."""
    raw = endpoint.strip()
    if "://" not in raw:
        raw = "tcp://" + raw
    parsed = urlparse(raw)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5556
    return host, port


class NtTickSubscriber:
    """
    Connect to NinjaTrader GC Tick Publisher (TCP JSON lines on port 5556).

    One JSON object per line, same schema as the former ZeroMQ payload.
    """

    def __init__(
        self,
        endpoint: str = "tcp://localhost:5556",
        topic: str = "gc_ticks",  # kept for API compatibility; unused on TCP
        recv_timeout_ms: int = 1000,
    ) -> None:
        self.endpoint = endpoint
        self.topic = topic
        self._timeout = max(recv_timeout_ms, 100) / 1000.0
        self._host, self._port = _parse_tcp_endpoint(endpoint)
        self._sock: socket.socket | None = None
        self._buf = ""
        self._connect()

    def _connect(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self._timeout)
        try:
            sock.connect((self._host, self._port))
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock = sock
            self._buf = ""
        except OSError:
            sock.close()
            self._sock = None

    def recv_tick(self) -> dict[str, Any] | None:
        """Receive one tick; None on timeout / reconnect wait."""
        if self._sock is None:
            self._connect()
            return None

        # Drain complete lines from buffer first
        while "\n" not in self._buf:
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                return None
            except OSError:
                self._connect()
                return None
            if not chunk:
                self._connect()
                return None
            self._buf += chunk.decode("utf-8", errors="ignore")

        line, _, rest = self._buf.partition("\n")
        self._buf = rest
        line = line.strip()
        if not line:
            return None
        try:
            return normalize_tick(json.loads(line))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None


class TickBuffer:
    """Thread-safe rolling tick buffer."""

    def __init__(self, max_hours: float = 48.0) -> None:
        self.max_hours = max_hours
        self._lock = threading.Lock()
        self._ticks: deque[dict[str, Any]] = deque()
        self.live = False
        self.last_tick_mono: float | None = None
        self.count = 0

    def append(self, tick: dict[str, Any]) -> None:
        with self._lock:
            self._ticks.append(tick)
            self.count += 1
            self.live = True
            self.last_tick_mono = time.monotonic()
            self._trim_unlocked()

    def _trim_unlocked(self) -> None:
        if not self._ticks:
            return
        cutoff = self._ticks[-1]["timestamp"] - pd.Timedelta(hours=self.max_hours)
        while self._ticks and self._ticks[0]["timestamp"] < cutoff:
            self._ticks.popleft()

    def to_dataframe(self) -> pd.DataFrame:
        with self._lock:
            if not self._ticks:
                return pd.DataFrame(
                    columns=["timestamp", "symbol", "price", "volume", "bid", "ask"]
                )
            return pd.DataFrame(list(self._ticks))

    def age_sec(self) -> float | None:
        if self.last_tick_mono is None:
            return None
        return time.monotonic() - self.last_tick_mono


def run_live_loop(
    subscriber: NtTickSubscriber,
    buffer: TickBuffer,
    stop_event: threading.Event,
    on_tick: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Background loop: receive NT ticks into buffer."""
    while not stop_event.is_set():
        tick = subscriber.recv_tick()
        if tick is None:
            continue
        if tick["volume"] <= 0:
            continue
        buffer.append(tick)
        if on_tick is not None:
            on_tick(tick)


def iter_csv_replay(
    df: pd.DataFrame,
    delay_sec: float = 0.0,
) -> Iterator[dict[str, Any]]:
    """Yield ticks from a DataFrame (optional pacing)."""
    for row in df.to_dict(orient="records"):
        yield normalize_tick(row)
        if delay_sec > 0:
            time.sleep(delay_sec)
