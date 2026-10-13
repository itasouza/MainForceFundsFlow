"""Configurable parameters for GC (100 oz) Main Force Flow system."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

CONFIG: dict[str, Any] = {
    "mode": "live",  # "live" or "backtest"
    "symbol": "GC",
    "contract_size_oz": 100,
    # NinjaTrader TCP tick feed (JSON lines; no NetMQ needed in NT)
    "nt_tick_transport": "tcp",  # "tcp" (default) | reserved
    "nt_zmq_subscribe": "tcp://localhost:5556",
    "nt_zmq_topic": "gc_ticks",

    # Signal ZeroMQ (signals out)
    "signal_zmq_publish": "tcp://*:5555",
    "signal_zmq_topic": "gold_mtf_flow",
    # Volume thresholds — GC-specific (100 oz)
    "mf_fixed_threshold_contracts": 10,
    "mf_dynamic_percentile": 90,
    "rolling_window_hours": 24,
    # Signal thresholds
    "threshold_1h": 0.15,
    "threshold_30m": 0.20,
    "threshold_10m": 0.30,
    # Engine
    "tick_buffer_hours": 48,
    "recompute_every_ticks": 20,
    "state_file": "signal_state.json",
    # Dashboard
    "dashboard_port": 8501,
    "chart_bars_display": 100,
    # Sessions (US/Eastern)
    "sessions": {
        "asian": ("18:00", "01:00"),
        "london": ("01:00", "08:00"),
        "new_york": ("08:00", "17:00"),
    },
}


def get_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a deep copy of CONFIG merged with optional overrides."""
    cfg = deepcopy(CONFIG)
    if overrides:
        cfg.update(overrides)
    return cfg
