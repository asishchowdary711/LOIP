"""Identity verification domain schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .evidence import EvidenceChain, ExtractedField
from loip.domains.qr_trust.schemas import QRTrustResult  # noqa: E402


class IdentityFlag(StrEnum):
    PAN_FORMAT_INVALID = "pan_format_invalid"
    PAN_NSDL_INACTIVE = "pan_nsdl_inactive"
    AADHAAR_FORMAT_INVALID = "aadhaar_format_invalid"
    AADHAAR_OTP_FAILED = "aadhaar_otp_failed"
    NAME_PAN_AADHAAR_MISMATCH = "name_pan_aadhaar_mismatch"
    DOB_MISMATCH = "dob_mismatch"
    DOCUMENT_METADATA_ANOMALY = "document_metadata_anomaly"
    ADDRESS_STATE_MISMATCH = "address_state_mismatch"
    SPOOF_DETECTED = "spoof_detected"
    FACE_MISMATCH = "face_mismatch"
    QR_SIGNATURE_INVALID = "qr_signature_invalid"
    QR_DATA_MISMATCH = "qr_data_mismatch"
    QR_TAMPERED = "qr_tampered"


class APIVerificationResult(BaseModel):
    source: str = Field(description="nsdl_api, uidai_api, etc.")
    matched: bool
    status: str | None = None
    raw_response: dict | None = Field(default=None, exclude=True)
    evidence: EvidenceChain | None = None


class EntityMatch(BaseModel):
    field_name: str
    sources: list[ExtractedField]
    similarity_score: float = Field(ge=0.0, le=1.0)
    threshold: float
    passed: bool


class IdentityVerificationResult(BaseModel):
    application_id: str
    identity_confidence: float = Field(ge=0.0, le=1.0)
    pan_verified: bool = False
    aadhaar_verified: bool = False
    face_verified: bool = False
    liveness_verified: bool = False
    face_match_score: float | None = None
    liveness_score: float | None = None
    entity_matches: list[EntityMatch] = Field(default_factory=list)
    api_results: list[APIVerificationResult] = Field(default_factory=list)
    tamper_flags: list[IdentityFlag] = Field(default_factory=list)
    mismatches: list[str] = Field(default_factory=list)
    evidence_chains: list[EvidenceChain] = Field(default_factory=list)
    qr_trust_result: QRTrustResult | None = Field(
        default=None,
        description="QR code trust analysis result (Aadhaar Secure QR + PAN QR)",
    )

    def has_flag(self, flag: IdentityFlag) -> bool:
        return flag in self.tamper_flags
