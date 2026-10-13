"""Incremental O(1) MTF Main Force engine for live GC ticks."""

from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from python_engine.signal_engine import (
    active_session,
    build_payload,
    composite_signal_from_context,
    detect_divergence,
)

TF_KEYS = ("10m", "30m", "1H")
TF_FLOOR = {"10m": "10min", "30m": "30min", "1H": "1h"}


@dataclass
class TickResult:
    """Outcome of processing one tick (hot path stays O(1))."""

    signal_payload: dict[str, Any] | None = None
    closed_1h: dict[str, Any] | None = None
    closed_10m: dict[str, Any] | None = None


def _round_price_level(price: float, tick_size: float = 0.10) -> float:
    """
    GC tick bin ($0.10). Equivalent to ``round(price, 1)`` when tick_size=0.10.

    Kept O(1) — no DataFrame.
    """
    if tick_size <= 0:
        return round(float(price), 1)
    # One decimal for GC; avoids float drift (e.g. 2675.299999 → 2675.3)
    return round(round(float(price) / tick_size) * tick_size, 1)


def _empty_footprint() -> dict[str, Any]:
    """Schema consumed by dashboard / future EA (MQL5 / NinjaScript)."""
    return {
        "price_levels": [],
        "mf_buy_vol": [],
        "mf_sell_vol": [],
        "net_mf_vol": [],
        "absorption_level": None,
        "absorption_volume": 0.0,
        "high": None,
        "low": None,
        "close": None,
    }


def _profiles_to_footprint(
    buy_profile: dict[float, float],
    sell_profile: dict[float, float],
    *,
    high: float | None = None,
    low: float | None = None,
    close: float | None = None,
) -> dict[str, Any]:
    """
    Finalize buy/sell dicts into array payload (bar-close only — not hot path).

    Absorption = price with largest |net MF volume| (buy − sell).
    Grid tip: do not park limit orders exactly on absorption_level — shift 2–4 ticks;
    net+ below price ≈ institutional floor; net− above ≈ institutional ceiling.
    """
    levels = sorted(set(buy_profile) | set(sell_profile))
    if not levels:
        out = _empty_footprint()
        out["high"] = high
        out["low"] = low
        out["close"] = close
        return out

    buys: list[float] = []
    sells: list[float] = []
    nets: list[float] = []
    abs_level: float | None = None
    abs_vol = 0.0
    for lv in levels:
        b = float(buy_profile.get(lv, 0.0))
        s = float(sell_profile.get(lv, 0.0))
        n = b - s
        buys.append(round(b, 4))
        sells.append(round(s, 4))
        nets.append(round(n, 4))
        if abs_level is None or abs(n) > abs(abs_vol):
            abs_level = float(lv)
            abs_vol = n

    return {
        "price_levels": [float(lv) for lv in levels],
        "mf_buy_vol": buys,
        "mf_sell_vol": sells,
        "net_mf_vol": nets,
        "absorption_level": abs_level,
        "absorption_volume": round(float(abs_vol), 4),
        "high": high,
        "low": low,
        "close": close,
    }


def _empty_bar(bar_start: pd.Timestamp | None = None) -> dict[str, Any]:
    return {
        "bar_start_time": bar_start,
        "is_open": bar_start is not None,
        "open": 0.0,
        "high": 0.0,
        "low": 0.0,
        "close": 0.0,
        "total_vol": 0.0,
        "mf_buy_vol": 0.0,
        "mf_sell_vol": 0.0,
        "retail_buy_vol": 0.0,
        "retail_sell_vol": 0.0,
        "mf_delta": 0.0,
        "mf_delta_norm": 0.0,
        "retail_delta": 0.0,
        "retail_delta_norm": 0.0,
        # Institutional footprint hot path: O(1) defaultdict bumps (no pandas)
        "mf_buy_profile": defaultdict(float),
        "mf_sell_profile": defaultdict(float),
    }


def _finalize_metrics(bar: dict[str, Any]) -> dict[str, Any]:
    # Plain dicts before deepcopy (defaultdict → JSON-safe)
    buy_prof = dict(bar.get("mf_buy_profile") or {})
    sell_prof = dict(bar.get("mf_sell_profile") or {})
    bar_plain = {**bar, "mf_buy_profile": buy_prof, "mf_sell_profile": sell_prof}
    out = deepcopy(bar_plain)
    mf_buy = float(out["mf_buy_vol"])
    mf_sell = float(out["mf_sell_vol"])
    rt_buy = float(out["retail_buy_vol"])
    rt_sell = float(out["retail_sell_vol"])
    mf_delta = mf_buy - mf_sell
    rt_delta = rt_buy - rt_sell
    out["mf_delta"] = mf_delta
    out["mf_delta_norm"] = mf_delta / (mf_buy + mf_sell + 1e-8)
    out["retail_delta"] = rt_delta
    out["retail_delta_norm"] = rt_delta / (rt_buy + rt_sell + 1e-8)
    out["institutional_footprint"] = _profiles_to_footprint(
        buy_prof,
        sell_prof,
        high=float(out["high"]),
        low=float(out["low"]),
        close=float(out["close"]),
    )
    out["is_open"] = False
    return out


def _bar_to_dashboard(bar: dict[str, Any]) -> dict[str, Any]:
    ts = bar.get("bar_start_time")
    return {
        "timestamp": pd.Timestamp(ts).isoformat() if ts is not None else None,
        "open": float(bar["open"]),
        "high": float(bar["high"]),
        "low": float(bar["low"]),
        "close": float(bar["close"]),
        "volume": float(bar["total_vol"]),
        "mf_delta_norm": float(bar["mf_delta_norm"]),
        "retail_delta_norm": float(bar["retail_delta_norm"]),
    }


class IncrementalMTFEngine:
    """
    Process each tick in amortized O(1).

    - Circular volume buffer for dynamic MF percentile (recomputed every N ticks)
    - Open bars updated in place for 10m / 30m / 1H
    - Signal evaluation + heavy persistence only when a 10m bar closes
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.mf_fixed = float(config["mf_fixed_threshold_contracts"])
        self.mf_percentile = float(config["mf_dynamic_percentile"])
        self.tick_size = float(config.get("tick_size", 0.10))
        self.rolling_window_hours = float(config.get("rolling_window_hours", 24))
        self.history_limit = int(config.get("chart_bars_display", 100))
        self.percentile_every = int(config.get("percentile_recompute_ticks", 1000))
        self.volume_buffer_maxlen = int(config.get("volume_buffer_maxlen", 20_000))

        self.volume_events: deque[tuple[pd.Timestamp, float]] = deque(
            maxlen=self.volume_buffer_maxlen
        )
        self.dynamic_percentile_value = self.mf_fixed
        self.ticks_since_percentile = 0

        self.current_bars: dict[str, dict[str, Any]] = {
            tf: _empty_bar() for tf in TF_KEYS
        }
        self.history_bars: dict[str, list[dict[str, Any]]] = {tf: [] for tf in TF_KEYS}
        # Last CLOSED bar footprint per TF (dashboard + EA JSON — not rolling history)
        self.last_closed_footprints: dict[str, dict[str, Any]] = {
            tf: _empty_footprint() for tf in TF_KEYS
        }

        self.last_known_direction = 0  # 1 buyer, -1 seller
        self.last_price: float | None = None
        self.last_tick_ts: pd.Timestamp | None = None
        self.tick_count = 0
        self.session_open_price: float | None = None

        self._closed_10m_this_tick = False
        self._last_payload: dict[str, Any] | None = None
        self.regime_info: dict[str, Any] = {
            "regime": int(config.get("active_regime", 1)),
            "label": "Strong Trend / Standard",
            "source": "default",
            "features": {},
        }

    def apply_runtime_config(self) -> None:
        """Refresh cached thresholds after PARAM_PROFILES / AI update."""
        self.mf_fixed = float(self.config["mf_fixed_threshold_contracts"])
        self.mf_percentile = float(self.config["mf_dynamic_percentile"])
        self.tick_size = float(self.config.get("tick_size", 0.10))

    def process_tick(self, tick: dict[str, Any]) -> TickResult:
        """
        Ingest one tick in amortized O(1).

        Returns TickResult with optional 10m signal payload and/or closed 1H bar
        (regime AI should run only when ``closed_1h`` is set).
        """
        self._closed_10m_this_tick = False
        price = float(tick["price"])
        volume = float(tick["volume"])
        if volume <= 0:
            return TickResult()

        ts = pd.Timestamp(tick["timestamp"])
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")

        self.tick_count += 1
        self.last_tick_ts = ts
        if self.session_open_price is None:
            self.session_open_price = price

        self._update_dynamic_threshold(ts, volume)
        is_buyer = self._lee_ready(tick, price)
        is_mf = (volume >= self.mf_fixed) and (volume >= self.dynamic_percentile_value)

        closed_10m: dict[str, Any] | None = None
        closed_1h: dict[str, Any] | None = None
        for tf in TF_KEYS:
            closed = self._update_bar(tf, ts, price, volume, is_buyer, is_mf)
            if tf == "10m" and closed is not None:
                closed_10m = closed
                self._closed_10m_this_tick = True
            if tf == "1H" and closed is not None:
                closed_1h = closed

        self.last_price = price
        payload = None
        if closed_10m is not None:
            # Respect volatile/news profile kill-switch for new grid bias
            if self.config.get("grid_paused"):
                payload = self._evaluate_and_build_payload(closed_10m, ts)
                if payload is not None:
                    payload["composite_signal"] = 0
                    payload["grid_paused"] = True
                    payload["confidence_score"] = 0.0
                    self._last_payload = payload
            else:
                payload = self._evaluate_and_build_payload(closed_10m, ts)
        return TickResult(signal_payload=payload, closed_1h=closed_1h, closed_10m=closed_10m)

    def snapshot_state(self) -> dict[str, Any]:
        """Lightweight dashboard state (no disk write)."""
        live_bars = [_bar_to_dashboard(b) for b in self.history_bars["10m"][-self.history_limit :]]
        # Include in-progress 10m bar for chart freshness
        cur = self.current_bars["10m"]
        if cur.get("is_open") and cur.get("bar_start_time") is not None:
            preview = _finalize_metrics(cur)
            live_bars = live_bars + [_bar_to_dashboard(preview)]
            live_bars = live_bars[-self.history_limit :]

        return {
            "mode": "live",
            "live": True,
            "tick_count": self.tick_count,
            "last_price": self.last_price,
            "session_open_price": self.session_open_price,
            "latest_signal": self._last_payload,
            "bars_10m": live_bars,
            "active_session": (
                active_session(self.last_tick_ts, self.config["sessions"])
                if self.last_tick_ts is not None
                else None
            ),
            "engine": "incremental",
            "mf_dynamic_threshold": round(float(self.dynamic_percentile_value), 4),
            "regime": self.regime_info,
            "thresholds": {
                "threshold_1h": self.config.get("threshold_1h"),
                "threshold_30m": self.config.get("threshold_30m"),
                "threshold_10m": self.config.get("threshold_10m"),
                "mf_fixed_threshold_contracts": self.config.get("mf_fixed_threshold_contracts"),
                "grid_paused": self.config.get("grid_paused", False),
            },
            # Persisted for Streamlit / future execution Strategy
            "institutional_footprint": self._institutional_footprint_bundle(),
        }

    def _institutional_footprint_bundle(self) -> dict[str, dict[str, Any]]:
        """Last-closed footprint for each TF (JSON-stable shallow copies)."""
        return {tf: dict(self.last_closed_footprints[tf]) for tf in TF_KEYS}

    def _update_dynamic_threshold(self, ts: pd.Timestamp, volume: float) -> None:
        self.volume_events.append((ts, volume))
        self.ticks_since_percentile += 1
        if self.ticks_since_percentile < self.percentile_every and len(self.volume_events) > 50:
            return
        self.ticks_since_percentile = 0
        cutoff = ts - pd.Timedelta(hours=self.rolling_window_hours)
        while self.volume_events and self.volume_events[0][0] < cutoff:
            self.volume_events.popleft()
        if not self.volume_events:
            self.dynamic_percentile_value = self.mf_fixed
            return
        vols = np.fromiter((v for _, v in self.volume_events), dtype=float, count=len(self.volume_events))
        self.dynamic_percentile_value = float(np.percentile(vols, self.mf_percentile))

    def _lee_ready(self, tick: dict[str, Any], price: float) -> bool:
        """Return True if buyer-initiated. Persists last direction on ties."""
        bid = tick.get("bid")
        ask = tick.get("ask")
        try:
            bid_f = float(bid) if bid is not None and not (isinstance(bid, float) and np.isnan(bid)) else None
            ask_f = float(ask) if ask is not None and not (isinstance(ask, float) and np.isnan(ask)) else None
        except (TypeError, ValueError):
            bid_f, ask_f = None, None

        if bid_f is not None and ask_f is not None and ask_f >= bid_f and bid_f > 0 and ask_f > 0:
            if price >= ask_f:
                self.last_known_direction = 1
                return True
            if price <= bid_f:
                self.last_known_direction = -1
                return False
            # Inside spread → tick rule / last direction

        if self.last_price is None:
            # First tick: neutral default buyer only if no prior direction
            if self.last_known_direction == 0:
                self.last_known_direction = 1
            return self.last_known_direction == 1

        if price > self.last_price:
            self.last_known_direction = 1
            return True
        if price < self.last_price:
            self.last_known_direction = -1
            return False

        # Tie: keep last known aggression (fixes buyer bias on flat prints)
        if self.last_known_direction == 0:
            self.last_known_direction = 1
        return self.last_known_direction == 1

    def _update_bar(
        self,
        tf: str,
        ts: pd.Timestamp,
        price: float,
        volume: float,
        is_buyer: bool,
        is_mf: bool,
    ) -> dict[str, Any] | None:
        bar_time = ts.floor(TF_FLOOR[tf])
        bar = self.current_bars[tf]
        closed: dict[str, Any] | None = None

        if not bar["is_open"]:
            bar = _empty_bar(bar_time)
            bar["open"] = price
            bar["high"] = price
            bar["low"] = price
            self.current_bars[tf] = bar
        elif bar["bar_start_time"] != bar_time:
            closed = _finalize_metrics(bar)
            self.last_closed_footprints[tf] = closed["institutional_footprint"]
            self.history_bars[tf].append(closed)
            if len(self.history_bars[tf]) > 500:
                self.history_bars[tf] = self.history_bars[tf][-500:]
            bar = _empty_bar(bar_time)
            bar["open"] = price
            bar["high"] = price
            bar["low"] = price
            self.current_bars[tf] = bar

        bar["close"] = price
        bar["high"] = max(float(bar["high"]), price)
        bar["low"] = min(float(bar["low"]), price)
        bar["total_vol"] += volume
        if is_mf:
            if is_buyer:
                bar["mf_buy_vol"] += volume
            else:
                bar["mf_sell_vol"] += volume
            # O(1): where is MF printing + Lee-Ready aggression (buy vs sell profile)
            level = _round_price_level(price, self.tick_size)
            if is_buyer:
                bar["mf_buy_profile"][level] += volume
            else:
                bar["mf_sell_profile"][level] += volume
        else:
            if is_buyer:
                bar["retail_buy_vol"] += volume
            else:
                bar["retail_sell_vol"] += volume
        return closed

    def _ctx_from_history(self) -> dict[str, dict[str, float]] | None:
        ctx: dict[str, dict[str, float]] = {}
        for tf in TF_KEYS:
            hist = self.history_bars[tf]
            if not hist:
                return None
            last = hist[-1]
            ctx[tf] = {
                "mf_delta_norm": float(last["mf_delta_norm"]),
                "retail_delta_norm": float(last["retail_delta_norm"]),
                "mf_delta": float(last["mf_delta"]),
            }
        return ctx

    def _evaluate_and_build_payload(
        self,
        closed_10m: dict[str, Any],
        as_of: pd.Timestamp,
    ) -> dict[str, Any] | None:
        ctx = self._ctx_from_history()
        if ctx is None:
            # Warmup: publish neutral snapshot from whatever TFs exist
            partial: dict[str, dict[str, float]] = {}
            for tf in TF_KEYS:
                if self.history_bars[tf]:
                    last = self.history_bars[tf][-1]
                    partial[tf] = {
                        "mf_delta_norm": float(last["mf_delta_norm"]),
                        "retail_delta_norm": float(last["retail_delta_norm"]),
                        "mf_delta": float(last["mf_delta"]),
                    }
                else:
                    partial[tf] = {
                        "mf_delta_norm": 0.0,
                        "retail_delta_norm": 0.0,
                        "mf_delta": 0.0,
                    }
            ctx = partial
            signal, conf = 0, 0.0
        else:
            signal, conf = composite_signal_from_context(
                ctx,
                threshold_1h=float(self.config["threshold_1h"]),
                threshold_30m=float(self.config["threshold_30m"]),
                threshold_10m=float(self.config["threshold_10m"]),
            )

        ts_close = pd.Timestamp(closed_10m["bar_start_time"]) + pd.Timedelta("10min")
        payload = build_payload(
            timestamp=ts_close.strftime("%Y-%m-%dT%H:%M:%SZ"),
            symbol=str(self.config["symbol"]),
            price=float(closed_10m["close"]),
            timeframes=ctx,
            composite_signal=signal,
            confidence_score=conf,
        )
        # Prefer detect_divergence already in build_payload; ensure flag present
        if "divergence_detected" not in payload:
            div, msg = detect_divergence(ctx)
            payload["divergence_detected"] = div
            payload["divergence_message"] = msg
        payload["session"] = active_session(ts_close, self.config["sessions"])
        # institutional_footprint: last closed 10m/30m/1H — EA-ready schema
        payload["institutional_footprint"] = self._institutional_footprint_bundle()
        self._last_payload = payload
        return payload


def run_incremental_on_ticks(
    ticks: list[dict[str, Any]] | pd.DataFrame,
    config: dict[str, Any],
    on_signal: Callable[[dict[str, Any]], None] | None = None,
) -> IncrementalMTFEngine:
    """Replay ticks through the incremental engine (tests / CSV warmup)."""
    engine = IncrementalMTFEngine(config)
    if isinstance(ticks, pd.DataFrame):
        records = ticks.to_dict(orient="records")
    else:
        records = ticks
    for row in records:
        result = engine.process_tick(row)
        if result.signal_payload is not None and on_signal is not None:
            on_signal(result.signal_payload)
    return engine
