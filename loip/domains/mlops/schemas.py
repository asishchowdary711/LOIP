"""MLOps domain schemas — model registry, feature views, drift monitoring, retraining."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ModelStage(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"


class DriftType(StrEnum):
    DATA_DRIFT = "data_drift"
    MODEL_DRIFT = "model_drift"
    TARGET_DRIFT = "target_drift"


class DriftSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RegisteredModel(BaseModel):
    model_name: str
    version: str
    stage: ModelStage = ModelStage.DEVELOPMENT
    run_id: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    holdout_score: float | None = Field(default=None, description="Validation score on holdout set")
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    promoted_at: datetime | None = None


class PromotionGate(BaseModel):
    model_name: str
    from_stage: ModelStage
    to_stage: ModelStage
    required_metric: str
    threshold: float
    actual_value: float | None = None
    passed: bool = False


class FeatureView(BaseModel):
    name: str
    domain: str = Field(description="identity, income, affordability, fraud, risk")
    features: list[str]
    entity_key: str = "application_id"
    online_store: str = "redis"
    offline_store: str = "postgresql"
    ttl_seconds: int = Field(default=86400, description="Feature freshness TTL")


class DriftAlert(BaseModel):
    alert_id: str
    model_name: str
    drift_type: DriftType
    severity: DriftSeverity
    feature_name: str | None = None
    drift_score: float = Field(ge=0.0, le=1.0)
    threshold: float
    details: str
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    acknowledged: bool = False


class RetrainingTrigger(BaseModel):
    trigger_id: str
    reason: str = Field(description="drift_alert, scheduled_weekly, override_feedback, manual")
    model_name: str
    drift_alert_id: str | None = None
    override_count: int = 0
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    new_model_version: str | None = None
