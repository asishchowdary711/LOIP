"""Traceability contract — defined once, enforced on every domain output."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ExtractionMethod(StrEnum):
    PADDLEOCR = "paddleocr"
    SURYA = "surya"
    QWEN2_5_VL = "qwen2.5-vl"
    DONUT = "donut"
    UIDAI_API = "uidai_api"
    NSDL_API = "nsdl_api"
    CIBIL_API = "cibil_api"
    EXPERIAN_API = "experian_api"
    DIGILOCKER = "digilocker"
    HUMAN_ENTRY = "human_entry"
    QR_DECODE = "qr_decode"


class DocumentType(StrEnum):
    PAN = "pan"
    AADHAAR = "aadhaar"
    SALARY_SLIP = "salary_slip"
    BANK_STATEMENT = "bank_statement"
    FORM16 = "form16"
    ITR = "itr"
    GST_RETURN = "gst_return"
    OFFER_LETTER = "offer_letter"
    PASSPORT = "passport"
    DRIVING_LICENCE = "driving_licence"


class ReconciliationMethod(StrEnum):
    SOURCE_TRUST_WEIGHTED = "source_trust_weighted"
    MAJORITY_VOTE = "majority_vote"
    HIGHEST_CONFIDENCE = "highest_confidence"
    API_AUTHORITATIVE = "api_authoritative"
    COMPUTED = "computed"


class BoundingBox(BaseModel):
    x0: int = Field(ge=0, le=1000)
    y0: int = Field(ge=0, le=1000)
    x1: int = Field(ge=0, le=1000)
    y1: int = Field(ge=0, le=1000)


class SourceLocation(BaseModel):
    document_id: str = Field(description="UUID linking to stored document in MinIO")
    document_type: DocumentType
    is_synthetic: bool = Field(default=False, description="True for generated test data")
    page_number: int | None = None
    coordinates: BoundingBox | None = Field(default=None, description="Normalized 0-1000 (LayoutLMv3 convention)")
    extraction_method: ExtractionMethod
    model_version: str = Field(description="e.g. paddleocr-4.0, qwen2.5-vl-7b-v1")


class ExtractedField(BaseModel):
    field_name: str = Field(description="e.g. pan_number, annual_income, employer_name")
    raw_value: str
    normalized_value: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    source: SourceLocation
    verified_by: list[str] = Field(default_factory=list, description="Verification model IDs or API names")


class EvidenceChain(BaseModel):
    chain_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    claim: str = Field(description="e.g. applicant_annual_income = ₹12,00,000")
    supporting: list[ExtractedField]
    contradicting: list[ExtractedField] = Field(default_factory=list)
    reconciled_value: str | float
    reconciliation_method: ReconciliationMethod
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
