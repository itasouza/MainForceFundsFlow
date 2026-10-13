"""Contract specs, thresholds, and ZeroMQ settings."""

from __future__ import annotations

from typing import Any, TypedDict


class ContractSpec(TypedDict):
    """Per-contract metadata for volume interpretation."""

    oz_per_contract: float
    default_fixed_volume_threshold: int


CONTRACT_SPECS: dict[str, ContractSpec] = {
    "GC": {"oz_per_contract": 100.0, "default_fixed_volume_threshold": 15},
    "MGC": {"oz_per_contract": 10.0, "default_fixed_volume_threshold": 50},
}

CONFIG: dict[str, Any] = {
    "contract_type": "MGC",  # "GC" or "MGC"
    "symbol": "MGC",
    "fixed_volume_threshold": 50,
    "dynamic_percentile": 90,
    "rolling_window_hours": 24,
    "threshold_1h": 0.15,
    "threshold_30m": 0.20,
    "threshold_10m": 0.30,
    "zmq_host": "127.0.0.1",
    "zmq_port": 5555,
    "panel_host": "127.0.0.1",
    "panel_port": 8765,
    "bar_timezone": "UTC",
}


def apply_contract_defaults(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Return a copy of CONFIG merged with optional overrides.

    Sets ``fixed_volume_threshold`` from the contract spec unless overridden.
    """
    overrides = cfg or {}
    out = {**CONFIG, **overrides}
    contract = str(out.get("contract_type", "MGC")).upper()
    if contract not in CONTRACT_SPECS:
        raise ValueError(f"Unknown contract_type: {contract}. Use GC or MGC.")
    spec = CONTRACT_SPECS[contract]
    out["symbol"] = out.get("symbol") or contract
    if "fixed_volume_threshold" not in overrides:
        out["fixed_volume_threshold"] = spec["default_fixed_volume_threshold"]
    return out
