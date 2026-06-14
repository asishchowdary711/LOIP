"""Train the affordability LightGBM model on synthetic data.

Run with: .venv-ml/bin/python -m scripts.training.train_affordability_lightgbm
"""

from __future__ import annotations

import csv
from pathlib import Path

import lightgbm as lgb
import numpy as np
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split

from loip.models.lightgbm_wrapper import CHECKPOINT_DIR, CHECKPOINT_PATH, FEATURE_ORDER

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "training" / "affordability_synthetic.csv"


def main() -> None:
    with open(DATA_PATH) as f:
        rows = list(csv.DictReader(f))

    X = np.array([[float(row[name]) for name in FEATURE_ORDER] for row in rows])
    y = np.array([float(row["label"]) for row in rows])

    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)

    train_set = lgb.Dataset(X_train, label=y_train, feature_name=FEATURE_ORDER)
    val_set = lgb.Dataset(X_val, label=y_val, feature_name=FEATURE_ORDER, reference=train_set)

    params = {
        "objective": "regression",
        "metric": "mae",
        "max_depth": 4,
        "learning_rate": 0.1,
        "num_leaves": 15,
        "verbose": -1,
        "seed": 42,
    }
    booster = lgb.train(
        params, train_set, num_boost_round=100,
        valid_sets=[val_set],
        callbacks=[lgb.early_stopping(10, verbose=False), lgb.log_evaluation(0)],
    )

    preds = booster.predict(X_val)
    mae = mean_absolute_error(y_val, preds)
    print(f"[affordability] val MAE: {mae:.4f} (n_val={len(y_val)})")

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(CHECKPOINT_PATH))
    print(f"Saved checkpoint to {CHECKPOINT_PATH}")


if __name__ == "__main__":
    main()
