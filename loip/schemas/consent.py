"""DPDP Act 2023 consent management schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ConsentPurpose(StrEnum):
    KYC_VERIFICATION = "kyc_verification"
    CREDIT_BUREAU_PULL = "credit_bureau_pull"
    INCOME_VERIFICATION = "income_verification"
    DOCUMENT_PROCESSING = "document_processing"
    DATA_STORAGE = "data_storage"


class ConsentStatus(StrEnum):
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class ConsentRecord(BaseModel):
    consent_id: str
    application_id: str
    data_principal_id: str = Field(description="Borrower identifier")
    purpose: ConsentPurpose
    consent_version: str
    consented_at: datetime
    withdrawn_at: datetime | None = None
    status: ConsentStatus = ConsentStatus.ACTIVE
    document_hash: str = Field(description="SHA-256 of consent document shown to borrower")
    ip_address: str | None = None
    user_agent: str | None = None


class DataDeletionRequest(BaseModel):
    application_id: str
    data_principal_id: str
    requested_at: datetime
    completed_at: datetime | None = None
    fields_deleted: list[str] = Field(default_factory=list)
    documents_deleted: list[str] = Field(default_factory=list, description="MinIO object IDs")
    audit_tombstone_id: str | None = None
