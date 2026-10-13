"""Persist latest engine state for the Streamlit dashboard (file + memory)."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import pandas as pd


class EngineStateStore:
    """Thread-safe state shared between main engine and dashboard via JSON file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self.state: dict[str, Any] = {
            "mode": "idle",
            "live": False,
            "tick_count": 0,
            "last_price": None,
            "session_open_price": None,
            "latest_signal": None,
            "signal_log": [],
            "bars_10m": [],
            "active_session": None,
        }

    def update(self, persist: bool = True, **kwargs: Any) -> None:
        with self._lock:
            self.state.update(kwargs)
            if persist:
                self._write_unlocked()

    def merge(self, data: dict[str, Any], persist: bool = True) -> None:
        """Merge a full snapshot dict into state."""
        with self._lock:
            # Preserve signal_log unless provided
            if "signal_log" not in data and "signal_log" in self.state:
                data = {**data, "signal_log": self.state["signal_log"]}
            self.state.update(data)
            if persist:
                self._write_unlocked()

    def push_signal(self, payload: dict[str, Any], max_log: int = 50, persist: bool = True) -> None:
        with self._lock:
            self.state["latest_signal"] = payload
            log = list(self.state.get("signal_log") or [])
            log.append(payload)
            self.state["signal_log"] = log[-max_log:]
            if persist:
                self._write_unlocked()

    def flush(self) -> None:
        with self._lock:
            self._write_unlocked()

    def set_bars_10m(self, bars: pd.DataFrame, limit: int = 100) -> None:
        with self._lock:
            if bars.empty:
                self.state["bars_10m"] = []
            else:
                tail = bars.tail(limit).copy()
                records = []
                for ts, row in tail.iterrows():
                    records.append(
                        {
                            "timestamp": pd.Timestamp(ts).isoformat(),
                            "open": float(row["open"]),
                            "high": float(row["high"]),
                            "low": float(row["low"]),
                            "close": float(row["close"]),
                            "volume": float(row["volume"]),
                            "mf_delta_norm": float(row["mf_delta_norm"]),
                            "retail_delta_norm": float(row["retail_delta_norm"]),
                        }
                    )
                self.state["bars_10m"] = records
            self._write_unlocked()

    def _write_unlocked(self) -> None:
        """Atomic-ish write with retries (Windows file locks from Streamlit)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.state, default=str)
        tmp = self.path.with_name(f"{self.path.stem}.{uuid.uuid4().hex}.tmp")
        tmp.write_text(payload, encoding="utf-8")
        last_err: Exception | None = None
        for attempt in range(8):
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError as exc:
                last_err = exc
                time.sleep(0.05 * (attempt + 1))
            except OSError as exc:
                last_err = exc
                time.sleep(0.05 * (attempt + 1))
        try:
            self.path.write_text(payload, encoding="utf-8")
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        if last_err is not None and not self.path.exists():
            raise last_err

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(self.state)
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return dict(self.state)
