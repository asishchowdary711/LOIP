"""QR Trust Verification domain schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class QRDocumentType(StrEnum):
    AADHAAR_SECURE_QR = "aadhaar_secure_qr"
    AADHAAR_TEXT_QR = "aadhaar_text_qr"
    PAN_QR = "pan_qr"
    UNKNOWN = "unknown"


class QRTrustFlag(StrEnum):
    QR_NOT_FOUND = "qr_not_found"
    QR_DECODE_FAILED = "qr_decode_failed"
    QR_SIGNATURE_INVALID = "qr_signature_invalid"
    QR_SIGNATURE_MISSING = "qr_signature_missing"
    QR_NAME_MISMATCH = "qr_name_mismatch"
    QR_DOB_MISMATCH = "qr_dob_mismatch"
    QR_ADDRESS_MISMATCH = "qr_address_mismatch"
    QR_ID_NUMBER_MISMATCH = "qr_id_number_mismatch"
    QR_ELA_ANOMALY = "qr_ela_anomaly"
    QR_EXIF_ANOMALY = "qr_exif_anomaly"
    QR_TAMPERED = "qr_tampered"


class QRDecodeResult(BaseModel):
    """Raw QR decode output from pyzbar or OpenCV."""

    raw_bytes: bytes
    raw_text: str | None = None
    qr_document_type: QRDocumentType = QRDocumentType.UNKNOWN
    decoder_used: str = Field(description="pyzbar | opencv | mock")
    decode_confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    bounding_box: tuple[int, int, int, int] | None = None


class AadhaarQRData(BaseModel):
    """Parsed fields from a UIDAI Aadhaar Secure QR XML payload."""

    uid: str | None = None
    full_name: str | None = None
    date_of_birth: str | None = None
    gender: str | None = None
    address: str | None = None
    mobile_last4: str | None = None
    email_hash: str | None = None
    signature_valid: bool = False
    raw_xml: str | None = Field(default=None, exclude=True)


class PANQRData(BaseModel):
    """Parsed fields from an Income Tax Department PAN QR code."""

    pan_number: str | None = None
    full_name: str | None = None
    date_of_birth: str | None = None
    father_name: str | None = None
    format_valid: bool = False


class QRDataMatch(BaseModel):
    """Cross-check result between a QR field value and its OCR counterpart."""

    field_name: str
    qr_value: str | None
    ocr_value: str | None
    similarity_score: float = Field(ge=0.0, le=1.0)
    threshold: float
    passed: bool


class QRTampering(BaseModel):
    """ELA + EXIF tampering analysis result for the document image."""

    ela_score: float = Field(ge=0.0, le=1.0, description="0=unmodified, 1=heavily altered")
    ela_anomaly: bool
    ela_threshold: float
    exif_anomalies: list[str] = Field(default_factory=list)
    exif_anomaly: bool
    overall_tampered: bool


class QRTrustResult(BaseModel):
    """Top-level result returned by QRTrustProcessor.verify()."""

    application_id: str
    mock_mode: bool = False

    aadhaar_qr: AadhaarQRData | None = None
    pan_qr: PANQRData | None = None
    decode_results: list[QRDecodeResult] = Field(default_factory=list)

    field_matches: list[QRDataMatch] = Field(default_factory=list)
    tampering: QRTampering | None = None

    flags: list[QRTrustFlag] = Field(default_factory=list)
    trust_score: float = Field(ge=0.0, le=1.0, default=1.0)
    evidence_chain_id: str | None = None

    def has_flag(self, flag: QRTrustFlag) -> bool:
        return flag in self.flags
