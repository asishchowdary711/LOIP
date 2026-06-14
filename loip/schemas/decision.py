"""Risk decisioning domain schemas — the final output of the onboarding pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from .affordability import AffordabilityResult
from .bureau import CreditBureauResult
from .evidence import EvidenceChain
from .fraud import FraudResult
from .identity import IdentityVerificationResult
from .income import IncomeResult


class Decision(StrEnum):
    APPROVE = "approve"
    REVIEW = "review"
    REJECT = "reject"


class EmploymentTier(int):
    """1=PSU/Govt, 2=Listed MNC, 3=Large Private, 4=Mid-size, 5=Startup/SME."""


class LoanApplication(BaseModel):
    application_id: str
    applicant_name: str
    loan_amount: float = Field(gt=0, description="In INR")
    tenure_months: int = Field(ge=12, le=60)
    employment_type: str = Field(description="salaried or self_employed")
    employment_tier: int = Field(ge=1, le=5)
    employer_name: str | None = None
    declared_monthly_income: float | None = None
    min_income_requirement: float = Field(default=20000.0, description="Lender-configurable floor (INR/month)")
    applied_at: datetime = Field(default_factory=datetime.utcnow)


class ReasonCode(BaseModel):
    code: str
    category: str = Field(description="identity, credit, income, affordability, risk")
    detail: str | None = None


class OnboardingDecision(BaseModel):
    application_id: str
    decision: Decision
    loan_amount: float | None = Field(default=None, description="Requested loan amount (INR), carried from the application")
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    risk_score: float | None = Field(default=None, ge=0.0, le=1.0, description="XGBoost ensemble score")
    review_flags: list[str] = Field(default_factory=list)
    identity_result: IdentityVerificationResult
    income_result: IncomeResult
    affordability_result: AffordabilityResult
    bureau_result: CreditBureauResult
    fraud_result: FraudResult | None = None
    risk_factors: list[str] = Field(default_factory=list, description="Top SHAP contributors (Phase 3)")
    copilot_narrative: str | None = Field(default=None, description="Qwen3 reviewer summary (Phase 3)")
    evidence_chains: list[EvidenceChain] = Field(default_factory=list)
    decided_at: datetime = Field(default_factory=datetime.utcnow)
