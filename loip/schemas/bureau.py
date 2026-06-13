"""Credit bureau (CIBIL / Experian / Equifax India) schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .evidence import EvidenceChain


class CreditBureauResult(BaseModel):
    application_id: str
    bureau: str = Field(description="cibil, experian, equifax")
    score: int = Field(ge=300, le=900, description="Credit score")
    active_loans: int = Field(ge=0)
    overdue_accounts: int = Field(ge=0)
    dpd_90_plus: bool = Field(description="Days-past-due ≥ 90 in last 24 months")
    total_outstanding: float = Field(ge=0.0)
    enquiry_count_last_6m: int = Field(ge=0)
    evidence: EvidenceChain
