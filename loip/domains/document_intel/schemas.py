"""Data types for the document intelligence pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class DocumentClass(StrEnum):
    PAN = "pan"
    AADHAAR = "aadhaar"
    SALARY_SLIP = "salary_slip"
    BANK_STATEMENT = "bank_statement"
    FORM16 = "form16"
    ITR = "itr"
    GST_RETURN = "gst_return"
    PASSPORT = "passport"
    DRIVING_LICENCE = "driving_licence"
    REJECT = "reject"


@dataclass
class ClassificationResult:
    document_class: DocumentClass
    confidence: float
    needs_review: bool = False
    logits: dict[str, float] = field(default_factory=dict)


@dataclass
class OCRBox:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x0, y0, x1, y1 in pixel coords


@dataclass
class OCRResult:
    boxes: list[OCRBox]
    mean_confidence: float
    engine: str  # "paddleocr" or "surya"
    raw_text: str = ""


@dataclass
class OCRConflict:
    primary: OCRResult
    secondary: OCRResult
    confidence_delta: float


@dataclass
class ExtractionField:
    name: str
    value: str
    confidence: float
    bbox: tuple[int, int, int, int] | None = None


@dataclass
class ExtractionResult:
    document_class: DocumentClass
    fields: list[ExtractionField]
    model: str  # "qwen2.5-vl" or "donut"
    overall_confidence: float


FIELD_SPECS: dict[DocumentClass, list[str]] = {
    DocumentClass.PAN: [
        "pan_number", "full_name", "fathers_name", "date_of_birth",
    ],
    DocumentClass.AADHAAR: [
        "aadhaar_number", "full_name", "date_of_birth", "gender",
        "address", "pincode",
    ],
    DocumentClass.SALARY_SLIP: [
        "employer_name", "employee_name", "employee_pan", "uan",
        "basic_pay", "hra", "gross_pay", "net_pay",
        "pf_deduction", "tds_deduction", "month", "year",
    ],
    DocumentClass.BANK_STATEMENT: [
        "bank_name", "account_number", "account_holder_name", "period",
        "opening_balance", "closing_balance",
    ],
    DocumentClass.FORM16: [
        "employer_tan", "employee_pan", "assessment_year",
        "gross_salary", "taxable_income", "tds_deducted"
    ],
    DocumentClass.ITR: [
        "pan", "assessment_year", "itr_type", "gross_total_income",
        "deductions", "total_income", "tax_payable", "refund"
    ],
    DocumentClass.GST_RETURN: [
        "gstin", "turnover_b2b", "turnover_b2c", "tax_period",
        "igst", "cgst", "sgst"
    ],
    DocumentClass.PASSPORT: [
        "passport_number", "full_name", "nationality", "expiry_date", "mrz_line"
    ],
    DocumentClass.DRIVING_LICENCE: [
        "dl_number", "full_name", "validity", "transport_category"
    ],
}

CLASSIFICATION_CONFIDENCE_THRESHOLD = 0.85
OCR_FALLBACK_THRESHOLD = 0.9
OCR_CONFLICT_THRESHOLD = 0.15
EXTRACTION_FALLBACK_THRESHOLD = 0.7
ANLS_GATE_THRESHOLD = 0.75
