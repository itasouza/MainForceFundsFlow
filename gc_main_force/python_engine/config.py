"""Configurable parameters for GC (100 oz) Main Force Flow system."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

# Regime class IDs (MarketRegimeClassifier output)
REGIME_CHOP = 0
REGIME_STANDARD = 1
REGIME_VOLATILE = 2

REGIME_LABELS: dict[int, str] = {
    REGIME_CHOP: "Chop / Low Volatility",
    REGIME_STANDARD: "Strong Trend / Standard",
    REGIME_VOLATILE: "High Volatility / News",
}

# Threshold profiles applied on 1H regime change (never trained live)
PARAM_PROFILES: dict[int, dict[str, Any]] = {
    REGIME_CHOP: {
        # Higher bars → fewer false signals in noise
        "mf_fixed_threshold_contracts": 12,
        "mf_dynamic_percentile": 92,
        "threshold_1h": 0.22,
        "threshold_30m": 0.28,
        "threshold_10m": 0.38,
        "grid_paused": False,
    },
    REGIME_STANDARD: {
        "mf_fixed_threshold_contracts": 10,
        "mf_dynamic_percentile": 90,
        "threshold_1h": 0.15,
        "threshold_30m": 0.20,
        "threshold_10m": 0.30,
        "grid_paused": False,
    },
    REGIME_VOLATILE: {
        # Wider filters + pause new grid entries (kill-switch friendly)
        "mf_fixed_threshold_contracts": 15,
        "mf_dynamic_percentile": 93,
        "threshold_1h": 0.25,
        "threshold_30m": 0.32,
        "threshold_10m": 0.42,
        "grid_paused": True,
    },
}

_MODELS_DIR = Path(__file__).resolve().parents[1] / "models"

CONFIG: dict[str, Any] = {
    "mode": "live",  # "live" or "backtest"
    "symbol": "GC",
    "contract_size_oz": 100,
    # GC CME minimum tick ($0.10) — MF institutional footprint price bins
    "tick_size": 0.10,
    # NinjaTrader tick feed
    # "zmq" = AddOn GcTickPublisher (NetMQ PUB, production)
    # "tcp" = Indicator GC Tick Publisher (JSON lines, fallback)
    "nt_tick_transport": "tcp",
    "nt_zmq_subscribe": "tcp://localhost:5556",
    "nt_zmq_topic": "gc_ticks",
    # Signal ZeroMQ (signals out)
    "signal_zmq_publish": "tcp://*:5555",
    "signal_zmq_topic": "gold_mtf_flow",
    # Volume thresholds — GC-specific (100 oz) — baseline = regime 1
    "mf_fixed_threshold_contracts": 10,
    "mf_dynamic_percentile": 90,
    "rolling_window_hours": 24,
    # Signal thresholds (baseline = regime 1)
    "threshold_1h": 0.15,
    "threshold_30m": 0.20,
    "threshold_10m": 0.30,
    "grid_paused": False,
    # Engine
    "tick_buffer_hours": 48,
    "recompute_every_ticks": 20,
    "live_engine": "incremental",
    "percentile_recompute_ticks": 1000,
    "volume_buffer_maxlen": 20000,
    "heartbeat_persist_sec": 2.0,
    "state_file": "signal_state.json",
    # AI regime (inference only; train offline via train_regime_model.py)
    "ai_regime_enabled": True,
    "regime_model_path": str(_MODELS_DIR / "regime_rf.joblib"),
    "ai_controls_file": "ai_controls.json",
    "active_regime": REGIME_STANDARD,
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


def apply_regime_profile(cfg: dict[str, Any], regime: int) -> dict[str, Any]:
    """
    Mutate ``cfg`` with PARAM_PROFILES[regime] (in-memory only).

    Returns the same dict for chaining.
    """
    profile = PARAM_PROFILES.get(int(regime), PARAM_PROFILES[REGIME_STANDARD])
    cfg.update(deepcopy(profile))
    cfg["active_regime"] = int(regime)
    return cfg
