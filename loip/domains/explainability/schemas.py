"""Explainability domain schemas — SHAP, LIME, and Qwen3 copilot outputs."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class SHAPContributor(BaseModel):
    feature_name: str
    shap_value: float
    feature_value: float | str
    direction: str = Field(description="positive or negative")


class SHAPExplanation(BaseModel):
    model_name: str = Field(description="e.g. risk_xgboost, affordability_lightgbm, income_xgboost")
    base_value: float
    output_value: float
    top_positive: list[SHAPContributor] = Field(default_factory=list, max_length=3)
    top_negative: list[SHAPContributor] = Field(default_factory=list, max_length=3)
    all_shap_values: dict[str, float] = Field(default_factory=dict)


class LIMEAttribution(BaseModel):
    field_name: str
    token: str
    weight: float
    bbox_x0: int | None = None
    bbox_y0: int | None = None
    bbox_x1: int | None = None
    bbox_y1: int | None = None


class LIMEExplanation(BaseModel):
    document_id: str
    document_type: str
    field_name: str
    attributions: list[LIMEAttribution] = Field(default_factory=list)
    prediction_confidence: float = Field(ge=0.0, le=1.0)


class CopilotNarrative(BaseModel):
    profile_summary: str = Field(description="3-sentence applicant profile summary")
    primary_decision_reason: str
    inconsistencies: list[str] = Field(default_factory=list, max_length=3)
    reviewer_questions: list[str] = Field(default_factory=list, max_length=2)
    raw_prompt: str | None = Field(default=None, exclude=True)
    model_id: str = Field(default="qwen3-32b")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExplainabilityResult(BaseModel):
    application_id: str
    shap_explanations: list[SHAPExplanation] = Field(default_factory=list)
    lime_explanations: list[LIMEExplanation] = Field(default_factory=list)
    copilot: CopilotNarrative | None = None
    risk_factors: list[str] = Field(default_factory=list, description="Top SHAP contributors as human-readable strings")
