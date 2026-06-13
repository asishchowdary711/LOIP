"""Explainability processor — orchestrates SHAP, LIME, and Qwen3 copilot."""

from __future__ import annotations

import logging
from typing import Any

from loip.domains.explainability.copilot import ReviewerCopilot
from loip.domains.explainability.lime_explainer import LIMEExplainer
from loip.domains.explainability.schemas import ExplainabilityResult
from loip.domains.explainability.shap_explainer import SHAPExplainer

logger = logging.getLogger(__name__)


class ExplainabilityProcessor:
    def __init__(self, mock_mode: bool = True, copilot_base_url: str = "http://localhost:8000/v1"):
        self.shap_explainer = SHAPExplainer(mock_mode=mock_mode)
        self.lime_explainer = LIMEExplainer(mock_mode=mock_mode)
        self.copilot = ReviewerCopilot(mock_mode=mock_mode, base_url=copilot_base_url)
        self.mock_mode = mock_mode

    async def explain(
        self,
        application_id: str,
        risk_features: dict[str, float],
        affordability_features: dict[str, float] | None = None,
        extraction_data: list[dict[str, Any]] | None = None,
        case_data: dict[str, Any] | None = None,
    ) -> ExplainabilityResult:
        shap_explanations = []

        risk_shap = self.shap_explainer.explain("risk_xgboost", risk_features)
        shap_explanations.append(risk_shap)

        if affordability_features:
            aff_shap = self.shap_explainer.explain("affordability_lightgbm", affordability_features)
            shap_explanations.append(aff_shap)

        risk_factors = []
        for contrib in risk_shap.top_positive:
            risk_factors.append(f"+{contrib.feature_name}: {contrib.shap_value:+.3f} (value={contrib.feature_value})")
        for contrib in risk_shap.top_negative:
            risk_factors.append(f"-{contrib.feature_name}: {contrib.shap_value:+.3f} (value={contrib.feature_value})")

        lime_explanations = []
        if extraction_data:
            for ext in extraction_data:
                lime_exp = self.lime_explainer.explain_extraction(
                    document_id=ext.get("document_id", ""),
                    document_type=ext.get("document_type", ""),
                    field_name=ext.get("field_name", ""),
                    extracted_value=ext.get("extracted_value", ""),
                    ocr_tokens=ext.get("ocr_tokens", []),
                    confidence=ext.get("confidence", 0.0),
                )
                lime_explanations.append(lime_exp)

        copilot_narrative = None
        if case_data:
            copilot_narrative = await self.copilot.generate_narrative(case_data)

        return ExplainabilityResult(
            application_id=application_id,
            shap_explanations=shap_explanations,
            lime_explanations=lime_explanations,
            copilot=copilot_narrative,
            risk_factors=risk_factors,
        )
