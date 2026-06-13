"""Compliance domain schemas — DPDP, PMLA/AML, RBI Digital Lending Guidelines."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class PEPStatus(StrEnum):
    CLEAR = "clear"
    MATCH = "match"
    REVIEW = "review"


class AMLRiskLevel(StrEnum):
    STANDARD = "standard"
    ENHANCED = "enhanced"


class KFSStatus(StrEnum):
    GENERATED = "generated"
    DISCLOSED = "disclosed"
    ACCEPTED = "accepted"


class CancellationStatus(StrEnum):
    ELIGIBLE = "eligible"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PEPScreeningResult(BaseModel):
    application_id: str
    applicant_name: str
    pan_number: str | None = None
    status: PEPStatus = PEPStatus.CLEAR
    matched_entries: list[str] = Field(default_factory=list)
    screened_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AMLCheckResult(BaseModel):
    application_id: str
    loan_amount: float
    risk_level: AMLRiskLevel = AMLRiskLevel.STANDARD
    is_high_value: bool = Field(default=False, description="Loan > 50L INR")
    pep_result: PEPScreeningResult | None = None
    requires_enhanced_dd: bool = False
    requires_senior_reviewer: bool = False
    sar_flagged: bool = Field(default=False, description="Suspicious Activity Report flagged")


class KeyFactStatement(BaseModel):
    application_id: str
    loan_amount: float
    tenure_months: int
    annual_rate: float
    apr: float = Field(description="Annual Percentage Rate including fees")
    processing_fee: float
    processing_fee_pct: float
    emi: float
    total_interest: float
    total_repayment: float
    lsp_name: str = Field(default="LOIP Platform", description="Lending Service Provider")
    lsp_role: str = Field(default="Technology Service Provider")
    status: KFSStatus = KFSStatus.GENERATED
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    disclosed_at: datetime | None = None
    accepted_at: datetime | None = None


class NACHMandate(BaseModel):
    application_id: str
    mandate_reference: str
    bank_account_number: str
    ifsc_code: str
    emi_amount: float
    start_date: str
    end_date: str
    frequency: str = "monthly"
    status: str = "active"


class CoolingOffRecord(BaseModel):
    application_id: str
    disbursed_at: datetime
    cooling_off_expires: datetime
    cancellation_status: CancellationStatus = CancellationStatus.ELIGIBLE
    cancelled_at: datetime | None = None


class PIIMaskingResult(BaseModel):
    original_field_count: int
    masked_field_count: int
    entities_detected: list[str] = Field(default_factory=list)


class DataResidencyCheck(BaseModel):
    service_name: str
    endpoint: str
    region: str
    is_india_region: bool
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
