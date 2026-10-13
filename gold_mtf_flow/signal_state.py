"""Thread-safe store for the latest MTF signal and history (panel backend)."""

from __future__ import annotations

import threading
import time
from copy import deepcopy
from typing import Any


class SignalStateStore:
    """Holds the latest JSON payload and a rolling history for the signal panel."""

    def __init__(self, history_size: int = 120) -> None:
        self._lock = threading.Lock()
        self._history_size = history_size
        self.latest: dict[str, Any] | None = None
        self.history: list[dict[str, Any]] = []
        self.source: str = "idle"
        self.connected: bool = False
        self.message_count: int = 0
        self._last_update_mono: float | None = None

    def push(self, payload: dict[str, Any], source: str) -> None:
        with self._lock:
            self.latest = deepcopy(payload)
            self.history.append(deepcopy(payload))
            if len(self.history) > self._history_size:
                self.history = self.history[-self._history_size :]
            self.source = source
            self.connected = True
            self.message_count += 1
            self._last_update_mono = time.monotonic()

    def set_disconnected(self, source: str = "zmq") -> None:
        with self._lock:
            self.connected = False
            self.source = source

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            age_sec: float | None = None
            if self._last_update_mono is not None:
                age_sec = time.monotonic() - self._last_update_mono
            return {
                "latest": deepcopy(self.latest),
                "history": deepcopy(self.history[-30:]),
                "source": self.source,
                "connected": self.connected,
                "message_count": self.message_count,
                "age_sec": age_sec,
            }
