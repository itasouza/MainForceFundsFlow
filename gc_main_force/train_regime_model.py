"""
Offline trainer for MarketRegimeClassifier.

Never run this in the live loop. Generates models/regime_rf.joblib.

Usage:
  python train_regime_model.py
  python train_regime_model.py --csv backtest/sample_data/gc_ticks_sample.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from python_engine.config import REGIME_CHOP, REGIME_STANDARD, REGIME_VOLATILE, get_config
from python_engine.incremental_engine import IncrementalMTFEngine
from python_engine.regime_classifier import FEATURE_NAMES, MarketRegimeClassifier
from python_engine.tick_receiver import load_ticks_csv


def _label_from_features(row: dict[str, float]) -> int:
    """Heuristic labels for bootstrapping (replace with researched labels later)."""
    vol = row["volatility_ratio"]
    mf = row["mf_dominance"]
    if vol >= 1.6:
        return REGIME_VOLATILE
    if vol <= 0.75 and mf < 0.20:
        return REGIME_CHOP
    return REGIME_STANDARD


def build_feature_table_from_ticks(ticks: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Replay ticks incrementally; collect features at each 1H close."""
    engine = IncrementalMTFEngine(cfg)
    clf = MarketRegimeClassifier(model_path=None)
    rows: list[dict] = []

    for rec in ticks.to_dict(orient="records"):
        result = engine.process_tick(rec)
        # process_tick now returns TickResult
        payload = result.signal_payload if hasattr(result, "signal_payload") else result
        closed_1h = getattr(result, "closed_1h", None)
        if payload is not None:
            # Find last 10m bar for win-rate tracking
            if engine.history_bars["10m"]:
                clf.record_10m_close(
                    engine.history_bars["10m"][-1],
                    int(payload.get("composite_signal", 0)),
                )
        if closed_1h is not None:
            feats = clf.build_features(closed_1h, cfg)
            feats["regime"] = _label_from_features(feats)
            rows.append(feats)
            clf._1h_bars.append(closed_1h)

    return pd.DataFrame(rows)


def synthesize_feature_rows(n: int = 3000, seed: int = 42) -> pd.DataFrame:
    """Fallback synthetic dataset when CSV is too short for 1H closes."""
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        vol = float(rng.lognormal(mean=0.0, sigma=0.35))
        mf = float(rng.uniform(0, 1))
        div = float(rng.integers(0, 2))
        session = float(rng.choice([0, 1, 2, 3]))
        win = float(rng.uniform(0.2, 0.8))
        feats = {
            "volatility_ratio": vol,
            "mf_dominance": mf,
            "retail_divergence": div,
            "session_code": session,
            "recent_win_rate": win,
        }
        feats["regime"] = _label_from_features(feats)
        rows.append(feats)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train GC regime RF offline")
    parser.add_argument("--csv", type=Path, default=None)
    parser.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "models" / "regime_rf.joblib",
    )
    args = parser.parse_args()

    cfg = get_config()
    if args.csv and args.csv.exists():
        ticks = load_ticks_csv(args.csv)
        df = build_feature_table_from_ticks(ticks, cfg)
        print(f"Feature rows from CSV 1H closes: {len(df)}")
        if len(df) < 80:
            print("Too few 1H closes — augmenting with synthetic rows")
            df = pd.concat([df, synthesize_feature_rows(2500)], ignore_index=True)
    else:
        print("No CSV / missing file — training on synthetic regime features")
        df = synthesize_feature_rows(3000)

    x = df[list(FEATURE_NAMES)].astype(float).values
    y = df["regime"].astype(int).values
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.2, random_state=42, stratify=y
    )
    model = RandomForestClassifier(
        n_estimators=120,
        max_depth=6,
        min_samples_leaf=5,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced",
    )
    model.fit(x_train, y_train)
    pred = model.predict(x_test)
    print(classification_report(y_test, pred, digits=3))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.out)
    print(f"Wrote model: {args.out}")


if __name__ == "__main__":
    main()
