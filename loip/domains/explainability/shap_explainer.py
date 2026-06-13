"""SHAP explainer for ML models (XGBoost risk ensemble, LightGBM affordability, XGBoost income)."""

from __future__ import annotations

import logging
from typing import Any

from loip.domains.explainability.schemas import SHAPContributor, SHAPExplanation

logger = logging.getLogger(__name__)

FEATURE_DISPLAY_NAMES: dict[str, str] = {
    "identity_confidence": "Identity Confidence",
    "income_confidence": "Income Confidence",
    "foir": "FOIR (Obligation Ratio)",
    "cibil_score_normalized": "CIBIL Score",
    "cashflow_stability": "Cashflow Stability",
    "employment_tier": "Employment Risk Tier",
    "loan_to_income_ratio": "Loan-to-Income Ratio",
    "liquidity_score": "Liquidity Score",
    "financial_stress_score": "Financial Stress",
    "affordability_score": "Affordability Score",
}


class SHAPExplainer:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self._explainer = None

    def _init_explainer(self, model: Any) -> None:
        if self.mock_mode:
            return
        try:
            import shap
            self._explainer = shap.TreeExplainer(model)
        except Exception:
            logger.warning("SHAP TreeExplainer init failed; falling back to mock", exc_info=True)
            self.mock_mode = True

    def explain(self, model_name: str, features: dict[str, float], model: Any = None) -> SHAPExplanation:
        if self.mock_mode:
            return self._mock_explain(model_name, features)
        return self._real_explain(model_name, features, model)

    def _real_explain(self, model_name: str, features: dict[str, float], model: Any) -> SHAPExplanation:
        import numpy as np
        import shap

        if self._explainer is None:
            self._init_explainer(model)

        feature_names = list(features.keys())
        feature_values = np.array([list(features.values())])
        shap_values = self._explainer.shap_values(feature_values)

        if isinstance(shap_values, list):
            shap_values = shap_values[0]
        shap_dict = dict(zip(feature_names, shap_values[0]))

        sorted_by_value = sorted(shap_dict.items(), key=lambda x: x[1])
        top_negative = [
            SHAPContributor(
                feature_name=FEATURE_DISPLAY_NAMES.get(k, k),
                shap_value=v,
                feature_value=features[k],
                direction="negative",
            )
            for k, v in sorted_by_value[:3]
            if v < 0
        ]
        top_positive = [
            SHAPContributor(
                feature_name=FEATURE_DISPLAY_NAMES.get(k, k),
                shap_value=v,
                feature_value=features[k],
                direction="positive",
            )
            for k, v in reversed(sorted_by_value[-3:])
            if v > 0
        ]

        return SHAPExplanation(
            model_name=model_name,
            base_value=float(self._explainer.expected_value),
            output_value=float(sum(shap_dict.values()) + self._explainer.expected_value),
            top_positive=top_positive,
            top_negative=top_negative,
            all_shap_values={FEATURE_DISPLAY_NAMES.get(k, k): round(v, 4) for k, v in shap_dict.items()},
        )

    def _mock_explain(self, model_name: str, features: dict[str, float]) -> SHAPExplanation:
        mock_shap: dict[str, float] = {}
        for i, (k, v) in enumerate(features.items()):
            sign = 1.0 if i % 2 == 0 else -1.0
            mock_shap[k] = round(sign * (0.15 - i * 0.03), 4)

        sorted_items = sorted(mock_shap.items(), key=lambda x: x[1])
        top_negative = [
            SHAPContributor(
                feature_name=FEATURE_DISPLAY_NAMES.get(k, k),
                shap_value=v,
                feature_value=features[k],
                direction="negative",
            )
            for k, v in sorted_items[:3]
            if v < 0
        ]
        top_positive = [
            SHAPContributor(
                feature_name=FEATURE_DISPLAY_NAMES.get(k, k),
                shap_value=v,
                feature_value=features[k],
                direction="positive",
            )
            for k, v in reversed(sorted_items[-3:])
            if v > 0
        ]

        return SHAPExplanation(
            model_name=model_name,
            base_value=0.5,
            output_value=0.5 + sum(mock_shap.values()),
            top_positive=top_positive,
            top_negative=top_negative,
            all_shap_values={FEATURE_DISPLAY_NAMES.get(k, k): v for k, v in mock_shap.items()},
        )
