"""Income intelligence domain schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .evidence import EvidenceChain


class IncomeFlag(StrEnum):
    SALARY_SLIP_VS_BANK_MISMATCH = "salary_slip_vs_bank_mismatch"
    EMPLOYER_NAME_MISMATCH = "employer_name_mismatch"
    PAN_ON_SLIP_MISMATCH = "pan_on_slip_mismatch"
    UAN_FORMAT_INVALID = "uan_format_invalid"
    SALARY_MISSING_MANDATORY_FIELDS = "salary_missing_mandatory_fields"
    INCOME_BELOW_RBI_MINIMUM = "income_below_rbi_minimum"
    BANK_CREDIT_VOLATILITY = "bank_credit_volatility"
    FORM16_ITR_MISMATCH = "form16_itr_mismatch"
    NO_SALARY_CREDIT_FOUND = "no_salary_credit_found"
    INCOME_INFLATION = "income_inflation"
    INCOME_DEFLATION = "income_deflation"


class SalaryCredit(BaseModel):
    amount: float
    date: str
    narration: str
    matched_employer: str | None = None


class IncomeSource(BaseModel):
    source_name: str = Field(description="salary_slip, bank_statement, form16, itr")
    annual_amount: float
    trust_weight: float = Field(ge=0.0, le=1.0)
    evidence: EvidenceChain


class IncomeResult(BaseModel):
    application_id: str
    segment: str = Field(description="salaried or self_employed")
    income_sources: list[IncomeSource] = Field(default_factory=list)
    reconciled_annual_income: float
    verified_monthly_income: float
    income_confidence: float = Field(ge=0.0, le=1.0)
    salary_credits: list[SalaryCredit] = Field(default_factory=list)
    anomaly_flags: list[IncomeFlag] = Field(default_factory=list)
    evidence_chains: list[EvidenceChain] = Field(default_factory=list)
