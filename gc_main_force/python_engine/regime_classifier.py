"""Market regime classifier — inference only (no live training)."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from python_engine.config import (
    PARAM_PROFILES,
    REGIME_CHOP,
    REGIME_LABELS,
    REGIME_STANDARD,
    REGIME_VOLATILE,
    apply_regime_profile,
)
from python_engine.signal_engine import active_session

FEATURE_NAMES = (
    "volatility_ratio",
    "mf_dominance",
    "retail_divergence",
    "session_code",
    "recent_win_rate",
)

SESSION_CODE = {"asian": 1, "london": 2, "new_york": 3, "off_hours": 0}


@dataclass
class RegimeDecision:
    regime: int
    label: str
    source: str  # "ai" | "manual" | "default"
    features: dict[str, float]
    changed: bool


class MarketRegimeClassifier:
    """
    Lightweight real-time regime inference.

    Call ``on_1h_close`` only when a 1H bar closes (not on every tick).
    Never calls ``fit`` / train in the live path.
    """

    def __init__(
        self,
        model_path: Path | str | None = None,
        atr_lookback: int = 24,
        default_regime: int = REGIME_STANDARD,
    ) -> None:
        self.default_regime = int(default_regime)
        self.atr_lookback = int(atr_lookback)
        self.model = None
        self.model_path = Path(model_path) if model_path else None
        self.current_regime = self.default_regime
        self._1h_bars: deque[dict[str, Any]] = deque(maxlen=max(atr_lookback + 5, 48))
        self._pending_signals: deque[dict[str, Any]] = deque(maxlen=50)
        self._closed_10m: deque[dict[str, Any]] = deque(maxlen=100)
        self._win_outcomes: deque[int] = deque(maxlen=10)
        self._load_model()

    def _load_model(self) -> None:
        if self.model_path is None or not self.model_path.exists():
            self.model = None
            return
        try:
            import joblib

            self.model = joblib.load(self.model_path)
        except Exception as exc:  # noqa: BLE001
            print(f"Regime model load failed ({self.model_path}): {exc} — using default regime")
            self.model = None

    def record_10m_close(self, bar: dict[str, Any], signal: int) -> None:
        """Track 10m closes for rolling win-rate feature (O(1))."""
        self._closed_10m.append(
            {
                "close": float(bar["close"]),
                "signal": int(signal),
                "bar_start": bar.get("bar_start_time"),
            }
        )
        # Resolve outcomes that now have +2 bars of forward data
        n = len(self._closed_10m)
        if n >= 3:
            entry = self._closed_10m[-3]
            later = self._closed_10m[-1]
            sig = int(entry["signal"])
            if sig == 0:
                return
            moved = float(later["close"]) - float(entry["close"])
            win = 1 if (sig > 0 and moved > 0) or (sig < 0 and moved < 0) else 0
            self._win_outcomes.append(win)

    def on_1h_close(
        self,
        bar_1h: dict[str, Any],
        cfg: dict[str, Any],
        controls: dict[str, Any] | None = None,
    ) -> RegimeDecision:
        """
        Run once per 1H bar close. Updates ``cfg`` in-place via PARAM_PROFILES when regime changes.
        """
        controls = controls or {}
        self._1h_bars.append(bar_1h)
        features = self.build_features(bar_1h, cfg)
        prev = self.current_regime

        # Kill switch / manual override from dashboard
        if controls.get("ai_enabled") is False:
            forced = controls.get("force_regime")
            regime = int(forced) if forced is not None else self.default_regime
            source = "manual" if forced is not None else "default"
        elif controls.get("force_regime") is not None:
            regime = int(controls["force_regime"])
            source = "manual"
        else:
            regime = self.predict(features)
            source = "ai" if self.model is not None else "default"

        regime = int(np.clip(regime, 0, 2))
        changed = regime != prev
        self.current_regime = regime
        if changed or source == "manual":
            apply_regime_profile(cfg, regime)

        return RegimeDecision(
            regime=regime,
            label=REGIME_LABELS.get(regime, str(regime)),
            source=source,
            features=features,
            changed=changed,
        )

    def predict(self, features: dict[str, float]) -> int:
        """Inference only. Falls back to standard regime on any failure."""
        if self.model is None:
            return self.default_regime
        try:
            x = np.array([[features[name] for name in FEATURE_NAMES]], dtype=float)
            pred = self.model.predict(x)
            return int(pred[0])
        except Exception as exc:  # noqa: BLE001
            print(f"Regime predict failed: {exc} — default {self.default_regime}")
            return self.default_regime

    def build_features(self, bar_1h: dict[str, Any], cfg: dict[str, Any]) -> dict[str, float]:
        mf = float(bar_1h.get("mf_delta_norm", 0.0))
        rt = float(bar_1h.get("retail_delta_norm", 0.0))
        ts = bar_1h.get("bar_start_time")
        if ts is None:
            session = "off_hours"
        else:
            session = active_session(pd.Timestamp(ts), cfg.get("sessions", {}))

        return {
            "volatility_ratio": float(self._volatility_ratio()),
            "mf_dominance": float(abs(mf)),
            "retail_divergence": 1.0 if (mf * rt) < 0 and abs(mf) > 0.05 and abs(rt) > 0.05 else 0.0,
            "session_code": float(SESSION_CODE.get(session, 0)),
            "recent_win_rate": float(self._recent_win_rate()),
        }

    def _true_ranges(self) -> list[float]:
        bars = list(self._1h_bars)
        if not bars:
            return []
        trs: list[float] = []
        prev_c = float(bars[0]["close"])
        for b in bars:
            h, l, c = float(b["high"]), float(b["low"]), float(b["close"])
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            trs.append(tr)
            prev_c = c
        return trs

    def _volatility_ratio(self) -> float:
        trs = self._true_ranges()
        if not trs:
            return 1.0
        current = trs[-1]
        window = trs[-self.atr_lookback :]
        avg = float(np.mean(window)) if window else current
        if avg <= 1e-12:
            return 1.0
        return float(current / avg)

    def _recent_win_rate(self) -> float:
        if not self._win_outcomes:
            return 0.5  # neutral prior during warmup
        return float(np.mean(self._win_outcomes))


def load_ai_controls(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"ai_enabled": True, "force_regime": None, "pause_grid": False}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {
            "ai_enabled": bool(data.get("ai_enabled", True)),
            "force_regime": data.get("force_regime", None),
            "pause_grid": bool(data.get("pause_grid", False)),
        }
    except (json.JSONDecodeError, OSError):
        return {"ai_enabled": True, "force_regime": None, "pause_grid": False}


def save_ai_controls(path: Path | str, controls: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ai_enabled": bool(controls.get("ai_enabled", True)),
        "force_regime": controls.get("force_regime", None),
        "pause_grid": bool(controls.get("pause_grid", False)),
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
