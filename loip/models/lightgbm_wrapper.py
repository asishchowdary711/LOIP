from pathlib import Path

CHECKPOINT_DIR = Path(__file__).resolve().parent / "checkpoints"
CHECKPOINT_PATH = CHECKPOINT_DIR / "lightgbm_affordability.txt"

# Fixed feature order — must match scripts/training/train_affordability_lightgbm.py
# and scripts/training/generate_synthetic_dataset.py.
FEATURE_ORDER = ["foir", "disposable_income", "liquidity_score"]

MOCK_PREDICTION = 0.85


class LightGBMWrapper:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self._model = None

        if not self.mock_mode:
            try:
                import lightgbm  # noqa: F401
            except ImportError:
                self.mock_mode = True

    def _load_model(self):
        if self._model is not None:
            return self._model

        if not CHECKPOINT_PATH.exists():
            return None

        import lightgbm

        self._model = lightgbm.Booster(model_file=str(CHECKPOINT_PATH))
        return self._model

    def predict(self, features: dict) -> float:
        if self.mock_mode:
            return MOCK_PREDICTION

        model = self._load_model()
        if model is None:
            return MOCK_PREDICTION

        import numpy as np

        ordered = np.array([[float(features.get(name, 0.0)) for name in FEATURE_ORDER]])
        prediction = model.predict(ordered)
        return float(prediction[0])
