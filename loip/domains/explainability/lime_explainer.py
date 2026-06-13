"""LIME explainer for document extraction — token-level attribution for extracted fields."""

from __future__ import annotations

import logging
from typing import Any

from loip.domains.explainability.schemas import LIMEAttribution, LIMEExplanation

logger = logging.getLogger(__name__)


class LIMEExplainer:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode

    def explain_extraction(
        self,
        document_id: str,
        document_type: str,
        field_name: str,
        extracted_value: str,
        ocr_tokens: list[dict[str, Any]],
        confidence: float,
    ) -> LIMEExplanation:
        if self.mock_mode:
            return self._mock_explain(document_id, document_type, field_name, extracted_value, ocr_tokens, confidence)
        return self._real_explain(document_id, document_type, field_name, extracted_value, ocr_tokens, confidence)

    def _real_explain(
        self,
        document_id: str,
        document_type: str,
        field_name: str,
        extracted_value: str,
        ocr_tokens: list[dict[str, Any]],
        confidence: float,
    ) -> LIMEExplanation:
        try:
            from lime.lime_text import LimeTextExplainer

            explainer = LimeTextExplainer(class_names=["not_field", "is_field"])
            full_text = " ".join(t.get("text", "") for t in ocr_tokens)

            def predict_fn(texts: list[str]) -> Any:
                import numpy as np
                results = []
                for text in texts:
                    tokens_in = text.split()
                    value_tokens = extracted_value.lower().split()
                    match_count = sum(1 for t in tokens_in if t.lower() in value_tokens)
                    score = min(match_count / max(len(value_tokens), 1), 1.0)
                    results.append([1.0 - score, score])
                return np.array(results)

            explanation = explainer.explain_instance(full_text, predict_fn, num_features=10, num_samples=100)

            token_lookup = {t.get("text", ""): t for t in ocr_tokens}
            attributions = []
            for token_text, weight in explanation.as_list():
                tok_data = token_lookup.get(token_text, {})
                bbox = tok_data.get("bbox", {})
                attributions.append(
                    LIMEAttribution(
                        field_name=field_name,
                        token=token_text,
                        weight=round(weight, 4),
                        bbox_x0=bbox.get("x0"),
                        bbox_y0=bbox.get("y0"),
                        bbox_x1=bbox.get("x1"),
                        bbox_y1=bbox.get("y1"),
                    )
                )

            return LIMEExplanation(
                document_id=document_id,
                document_type=document_type,
                field_name=field_name,
                attributions=sorted(attributions, key=lambda a: abs(a.weight), reverse=True),
                prediction_confidence=confidence,
            )
        except Exception:
            logger.warning("LIME explanation failed; falling back to mock", exc_info=True)
            return self._mock_explain(document_id, document_type, field_name, extracted_value, ocr_tokens, confidence)

    def _mock_explain(
        self,
        document_id: str,
        document_type: str,
        field_name: str,
        extracted_value: str,
        ocr_tokens: list[dict[str, Any]],
        confidence: float,
    ) -> LIMEExplanation:
        value_tokens = extracted_value.lower().split()
        attributions = []
        for tok in ocr_tokens[:15]:
            text = tok.get("text", "")
            is_match = text.lower() in value_tokens
            weight = 0.85 if is_match else -0.05
            bbox = tok.get("bbox", {})
            attributions.append(
                LIMEAttribution(
                    field_name=field_name,
                    token=text,
                    weight=weight,
                    bbox_x0=bbox.get("x0"),
                    bbox_y0=bbox.get("y0"),
                    bbox_x1=bbox.get("x1"),
                    bbox_y1=bbox.get("y1"),
                )
            )

        return LIMEExplanation(
            document_id=document_id,
            document_type=document_type,
            field_name=field_name,
            attributions=sorted(attributions, key=lambda a: abs(a.weight), reverse=True),
            prediction_confidence=confidence,
        )
