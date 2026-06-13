"""Human review domain schemas — review queue, override actions, feedback loop."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from loip.schemas.decision import Decision


class ReviewStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ESCALATED = "escalated"


class OverrideDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    ESCALATE = "escalate"


class OverrideReasonCode(StrEnum):
    INCOME_VERIFIED_MANUALLY = "income_verified_manually"
    IDENTITY_CONFIRMED_BY_VKYC = "identity_confirmed_by_vkyc"
    EMPLOYER_VERIFIED_EXTERNALLY = "employer_verified_externally"
    DOCUMENTS_RESUBMITTED = "documents_resubmitted"
    FRAUD_CONFIRMED = "fraud_confirmed"
    ADDITIONAL_COLLATERAL = "additional_collateral"
    POLICY_EXCEPTION = "policy_exception"
    DATA_ENTRY_ERROR = "data_entry_error"
    SYSTEM_ERROR_CORRECTION = "system_error_correction"
    OTHER = "other"


class ReviewCase(BaseModel):
    case_id: str
    application_id: str
    applicant_name: str
    loan_amount: float
    system_decision: Decision
    risk_score: float | None = None
    foir: float | None = None
    cibil_score: int | None = None
    primary_reason_code: str | None = None
    review_flags: list[str] = Field(default_factory=list)
    status: ReviewStatus = ReviewStatus.PENDING
    assigned_to: str | None = None
    onboarding_decision: Any = Field(default=None, exclude=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    age_in_queue_minutes: int = 0


class ReviewQueueFilters(BaseModel):
    status: ReviewStatus | None = None
    assigned_to: str | None = None
    min_risk_score: float | None = None
    sort_by: str = Field(default="risk_score", description="risk_score, created_at, loan_amount")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class OverrideRequest(BaseModel):
    reviewer_id: str
    override_decision: OverrideDecision
    reason_code: OverrideReasonCode
    notes: str = Field(min_length=10, max_length=2000, description="Mandatory free-text justification")


class OverrideRecord(BaseModel):
    override_id: str
    case_id: str
    application_id: str
    original_decision: Decision
    override_decision: OverrideDecision
    reason_code: OverrideReasonCode
    notes: str
    reviewer_id: str
    feature_snapshot: dict = Field(default_factory=dict, description="Feature vector at time of override for retraining")
    overridden_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReviewQueueSummary(BaseModel):
    total_pending: int = 0
    total_in_progress: int = 0
    total_completed: int = 0
    total_escalated: int = 0
    avg_age_minutes: float = 0.0
