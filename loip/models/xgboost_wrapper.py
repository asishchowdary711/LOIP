from pathlib import Path

CHECKPOINT_DIR = Path(__file__).resolve().parent / "checkpoints"

# Fixed feature order per task — must match scripts/training/train_*_xgboost.py
# and scripts/training/generate_synthetic_dataset.py.
FEATURE_ORDER = {
    "income_confidence": ["salary_slip_amount", "bank_credit_amount", "anomalies"],
    "risk_score": [
        "identity_confidence", "income_confidence", "foir", "cibil_score_normalized",
        "cashflow_stability", "employment_tier", "loan_to_income_ratio",
    ],
}

MOCK_PREDICTIONS = {
    "income_confidence": 0.85,
    "risk_score": 0.82,
}


class XGBoostWrapper:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self._models: dict[str, object] = {}

        if not self.mock_mode:
            try:
                import xgboost  # noqa: F401
            except ImportError:
                self.mock_mode = True

    def _load_model(self, task: str):
        if task in self._models:
            return self._models[task]

        import xgboost

        checkpoint_path = CHECKPOINT_DIR / f"xgboost_{task}.json"
        if not checkpoint_path.exists():
            return None

        booster = xgboost.Booster()
        booster.load_model(str(checkpoint_path))
        self._models[task] = booster
        return booster

    def predict(self, features: dict, task: str) -> float:
        if task not in FEATURE_ORDER:
            raise ValueError(f"Unknown task: {task!r}, expected one of {list(FEATURE_ORDER)}")

        if self.mock_mode:
            return MOCK_PREDICTIONS[task]

        booster = self._load_model(task)
        if booster is None:
            return MOCK_PREDICTIONS[task]

        import xgboost

        ordered = [float(features.get(name, 0.0)) for name in FEATURE_ORDER[task]]
        dmatrix = xgboost.DMatrix([ordered], feature_names=FEATURE_ORDER[task])
        prediction = booster.predict(dmatrix)
        return float(prediction[0])
