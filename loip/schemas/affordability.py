"""Affordability intelligence domain schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .evidence import EvidenceChain


class AffordabilityFlag(StrEnum):
    FOIR_EXCEEDED = "foir_exceeded"
    FOIR_MARGINAL = "foir_marginal"
    CASHFLOW_UNSTABLE = "cashflow_unstable"
    FINANCIAL_STRESS_HIGH = "financial_stress_high"
    DISPOSABLE_INCOME_INSUFFICIENT = "disposable_income_insufficient"


class AffordabilityResult(BaseModel):
    application_id: str
    verified_monthly_income: float
    income_confidence: float = Field(ge=0.0, le=1.0)
    income_evidence: list[EvidenceChain] = Field(default_factory=list)
    existing_obligations: float
    proposed_emi: float
    total_obligations: float
    foir: float = Field(ge=0.0, le=1.0, description="Fixed Obligation to Income Ratio")
    dti: float = Field(ge=0.0, le=1.0, description="Debt to Income — same as FOIR, kept for completeness")
    disposable_income: float
    liquidity_score: float = Field(ge=0.0, le=1.0)
    cashflow_stability: float = Field(ge=0.0, le=1.0)
    financial_stress_score: float = Field(ge=0.0, le=1.0)
    affordability_score: float = Field(ge=0.0, le=1.0, description="LightGBM composite score")
    affordability_confidence: float = Field(ge=0.0, le=1.0)
    anomaly_flags: list[AffordabilityFlag] = Field(default_factory=list)
    evidence_chains: list[EvidenceChain] = Field(default_factory=list)
