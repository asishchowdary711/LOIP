"""Train the income_confidence XGBoost model on synthetic data.

Run with: .venv-ml/bin/python -m scripts.training.train_income_xgboost
"""

from __future__ import annotations

import csv
from pathlib import Path

import xgboost as xgb
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split

from loip.models.xgboost_wrapper import CHECKPOINT_DIR, FEATURE_ORDER

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "training" / "income_synthetic.csv"
TASK = "income_confidence"


def main() -> None:
    with open(DATA_PATH) as f:
        rows = list(csv.DictReader(f))

    feature_names = FEATURE_ORDER[TASK]
    X = [[float(row[name]) for name in feature_names] for row in rows]
    y = [float(row["label"]) for row in rows]

    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)

    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=feature_names)
    dval = xgb.DMatrix(X_val, label=y_val, feature_names=feature_names)

    params = {
        "objective": "reg:squarederror",
        "max_depth": 4,
        "eta": 0.1,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "seed": 42,
    }
    booster = xgb.train(
        params, dtrain, num_boost_round=100,
        evals=[(dval, "val")], early_stopping_rounds=10, verbose_eval=False,
    )

    preds = booster.predict(dval)
    mae = mean_absolute_error(y_val, preds)
    print(f"[{TASK}] val MAE: {mae:.4f} (n_val={len(y_val)})")

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CHECKPOINT_DIR / f"xgboost_{TASK}.json"
    booster.save_model(str(out_path))
    print(f"Saved checkpoint to {out_path}")


if __name__ == "__main__":
    main()
