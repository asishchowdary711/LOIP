"""Compliance processor — DPDP consent enforcement, PMLA/AML, RBI DLG, PII masking."""

from __future__ import annotations

import logging
import math
import re
import uuid
from datetime import UTC, datetime, timedelta

from loip.domains.compliance.schemas import (
    AMLCheckResult,
    AMLRiskLevel,
    CancellationStatus,
    CoolingOffRecord,
    DataResidencyCheck,
    KFSStatus,
    KeyFactStatement,
    NACHMandate,
    PEPScreeningResult,
    PEPStatus,
    PIIMaskingResult,
)
from loip.schemas.consent import ConsentPurpose, ConsentRecord, ConsentStatus, DataDeletionRequest

logger = logging.getLogger(__name__)

HIGH_VALUE_THRESHOLD = 5_000_000
COOLING_OFF_DAYS = 3
PROCESSING_FEE_PCT = 0.02

PAN_PATTERN = re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]")
AADHAAR_PATTERN = re.compile(r"\d{4}\s?\d{4}\s?\d{4}")
PHONE_PATTERN = re.compile(r"(?:\+91[\s-]?)?[6-9]\d{9}")
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


class ComplianceProcessor:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self._consent_store: dict[str, list[ConsentRecord]] = {}
        self._kfs_store: dict[str, KeyFactStatement] = {}
        self._cooling_off_store: dict[str, CoolingOffRecord] = {}
        self._deletion_log: list[DataDeletionRequest] = []
        self._analyzer = None
        self._anonymizer = None

        if not self.mock_mode:
            try:
                from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer  # type: ignore[import-not-found]
                from presidio_anonymizer import AnonymizerEngine  # type: ignore[import-not-found]

                analyzer = AnalyzerEngine()
                analyzer.registry.add_recognizer(PatternRecognizer(
                    supported_entity="PAN_NUMBER",
                    patterns=[Pattern(name="pan_pattern", regex=PAN_PATTERN.pattern, score=0.85)],
                ))
                analyzer.registry.add_recognizer(PatternRecognizer(
                    supported_entity="AADHAAR_NUMBER",
                    patterns=[Pattern(name="aadhaar_pattern", regex=AADHAAR_PATTERN.pattern, score=0.85)],
                ))
                self._analyzer = analyzer
                self._anonymizer = AnonymizerEngine()
            except Exception:
                logger.warning("Presidio unavailable, falling back to regex-based PII masking", exc_info=True)
                self.mock_mode = True

    # --- DPDP Consent Management ---

    def record_consent(
        self,
        application_id: str,
        data_principal_id: str,
        purpose: ConsentPurpose,
        consent_version: str,
        document_hash: str,
        ip_address: str | None = None,
    ) -> ConsentRecord:
        record = ConsentRecord(
            consent_id=str(uuid.uuid4()),
            application_id=application_id,
            data_principal_id=data_principal_id,
            purpose=purpose,
            consent_version=consent_version,
            consented_at=datetime.now(UTC),
            document_hash=document_hash,
            ip_address=ip_address,
        )
        self._consent_store.setdefault(application_id, []).append(record)
        return record

    def verify_consent(self, application_id: str, purpose: ConsentPurpose) -> bool:
        records = self._consent_store.get(application_id, [])
        return any(r.purpose == purpose and r.status == ConsentStatus.ACTIVE for r in records)

    def withdraw_consent(self, application_id: str, purpose: ConsentPurpose) -> bool:
        records = self._consent_store.get(application_id, [])
        withdrawn = False
        for r in records:
            if r.purpose == purpose and r.status == ConsentStatus.ACTIVE:
                r.status = ConsentStatus.WITHDRAWN
                r.withdrawn_at = datetime.now(UTC)
                withdrawn = True
        return withdrawn

    def get_consent_records(self, application_id: str) -> list[ConsentRecord]:
        return self._consent_store.get(application_id, [])

    # --- DPDP Data Deletion ---

    def delete_personal_data(self, application_id: str, data_principal_id: str) -> DataDeletionRequest:
        deletion = DataDeletionRequest(
            application_id=application_id,
            data_principal_id=data_principal_id,
            requested_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            fields_deleted=[
                "applicant_name", "pan_number", "aadhaar_number",
                "phone", "email", "address", "employer_name",
                "bank_account_number",
            ],
            documents_deleted=[f"{application_id}/pan.pdf", f"{application_id}/aadhaar.pdf"],
            audit_tombstone_id=str(uuid.uuid4()),
        )
        self._deletion_log.append(deletion)
        logger.info("Personal data deleted for application %s (tombstone: %s)", application_id, deletion.audit_tombstone_id)
        return deletion

    def get_data_summary(self, application_id: str) -> dict:
        consents = self.get_consent_records(application_id)
        return {
            "application_id": application_id,
            "consent_records": [c.model_dump() for c in consents],
            "data_categories_held": [
                "identity_documents", "income_documents", "credit_bureau_data",
                "application_form_data", "decision_records",
            ],
            "retention_policy": "As per DPDP Act 2023 — deleted upon consent withdrawal or data principal request",
        }

    # --- PMLA / AML ---

    def screen_pep(self, application_id: str, applicant_name: str, pan: str | None = None) -> PEPScreeningResult:
        if self.mock_mode:
            return PEPScreeningResult(
                application_id=application_id,
                applicant_name=applicant_name,
                pan_number=pan,
                status=PEPStatus.CLEAR,
            )
        return PEPScreeningResult(
            application_id=application_id,
            applicant_name=applicant_name,
            pan_number=pan,
            status=PEPStatus.CLEAR,
        )

    def check_aml(self, application_id: str, loan_amount: float, fraud_score: float = 0.0) -> AMLCheckResult:
        is_high_value = loan_amount > HIGH_VALUE_THRESHOLD
        pep_result = self.screen_pep(application_id, "")

        sar_flagged = fraud_score > 0.80
        requires_enhanced = is_high_value or pep_result.status == PEPStatus.MATCH
        risk_level = AMLRiskLevel.ENHANCED if requires_enhanced else AMLRiskLevel.STANDARD

        return AMLCheckResult(
            application_id=application_id,
            loan_amount=loan_amount,
            risk_level=risk_level,
            is_high_value=is_high_value,
            pep_result=pep_result,
            requires_enhanced_dd=requires_enhanced,
            requires_senior_reviewer=is_high_value,
            sar_flagged=sar_flagged,
        )

    # --- RBI Digital Lending Guidelines ---

    def generate_kfs(
        self,
        application_id: str,
        loan_amount: float,
        tenure_months: int,
        annual_rate: float,
        processing_fee_pct: float = PROCESSING_FEE_PCT,
    ) -> KeyFactStatement:
        processing_fee = loan_amount * processing_fee_pct
        monthly_rate = annual_rate / 12 / 100
        if monthly_rate > 0:
            emi = loan_amount * monthly_rate * (1 + monthly_rate) ** tenure_months / ((1 + monthly_rate) ** tenure_months - 1)
        else:
            emi = loan_amount / tenure_months
        emi = round(emi, 2)
        total_repayment = round(emi * tenure_months, 2)
        total_interest = round(total_repayment - loan_amount, 2)

        total_cost = total_interest + processing_fee
        apr = round(((total_cost / loan_amount) / (tenure_months / 12)) * 100, 2)

        kfs = KeyFactStatement(
            application_id=application_id,
            loan_amount=loan_amount,
            tenure_months=tenure_months,
            annual_rate=annual_rate,
            apr=apr,
            processing_fee=round(processing_fee, 2),
            processing_fee_pct=processing_fee_pct * 100,
            emi=emi,
            total_interest=total_interest,
            total_repayment=total_repayment,
        )
        self._kfs_store[application_id] = kfs
        return kfs

    def disclose_kfs(self, application_id: str) -> KeyFactStatement | None:
        kfs = self._kfs_store.get(application_id)
        if kfs:
            kfs.status = KFSStatus.DISCLOSED
            kfs.disclosed_at = datetime.now(UTC)
        return kfs

    def accept_kfs(self, application_id: str) -> KeyFactStatement | None:
        kfs = self._kfs_store.get(application_id)
        if kfs:
            kfs.status = KFSStatus.ACCEPTED
            kfs.accepted_at = datetime.now(UTC)
        return kfs

    # --- Cooling-Off Period ---

    def start_cooling_off(self, application_id: str) -> CoolingOffRecord:
        now = datetime.now(UTC)
        record = CoolingOffRecord(
            application_id=application_id,
            disbursed_at=now,
            cooling_off_expires=now + timedelta(days=COOLING_OFF_DAYS),
        )
        self._cooling_off_store[application_id] = record
        return record

    def cancel_within_cooling_off(self, application_id: str) -> CoolingOffRecord | None:
        record = self._cooling_off_store.get(application_id)
        if record is None:
            return None
        now = datetime.now(UTC)
        if now > record.cooling_off_expires:
            record.cancellation_status = CancellationStatus.EXPIRED
            return record
        record.cancellation_status = CancellationStatus.CANCELLED
        record.cancelled_at = now
        return record

    # --- PII Masking ---

    @staticmethod
    def mask_aadhaar(value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) == 12:
            return f"**** **** {digits[-4:]}"
        return value

    @staticmethod
    def mask_pan(value: str) -> str:
        if PAN_PATTERN.fullmatch(value):
            return f"{value[:5]}***{value[-1]}"
        return value

    @staticmethod
    def mask_phone(value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) >= 10:
            return f"******{digits[-4:]}"
        return value

    @staticmethod
    def mask_email(value: str) -> str:
        if "@" in value:
            local, domain = value.split("@", 1)
            masked_local = local[0] + "***" if local else "***"
            return f"{masked_local}@{domain}"
        return value

    def mask_pii_in_text(self, text: str) -> tuple[str, PIIMaskingResult]:
        if not self.mock_mode and self._analyzer is not None and self._anonymizer is not None:
            return self._mask_pii_with_presidio(text)

        entities: list[str] = []
        masked = text
        count = 0

        for match in PAN_PATTERN.finditer(text):
            masked = masked.replace(match.group(), self.mask_pan(match.group()))
            entities.append("PAN")
            count += 1

        for match in AADHAAR_PATTERN.finditer(masked):
            masked = masked.replace(match.group(), self.mask_aadhaar(match.group()))
            entities.append("AADHAAR")
            count += 1

        for match in PHONE_PATTERN.finditer(masked):
            masked = masked.replace(match.group(), self.mask_phone(match.group()))
            entities.append("PHONE")
            count += 1

        for match in EMAIL_PATTERN.finditer(masked):
            masked = masked.replace(match.group(), self.mask_email(match.group()))
            entities.append("EMAIL")
            count += 1

        result = PIIMaskingResult(
            original_field_count=len(PAN_PATTERN.findall(text)) + len(AADHAAR_PATTERN.findall(text)),
            masked_field_count=count,
            entities_detected=list(set(entities)),
        )
        return masked, result

    def _mask_pii_with_presidio(self, text: str) -> tuple[str, PIIMaskingResult]:
        from presidio_anonymizer.entities import OperatorConfig  # type: ignore[import-not-found]

        analyzer_results = self._analyzer.analyze(
            text=text,
            language="en",
            entities=["PAN_NUMBER", "AADHAAR_NUMBER", "PHONE_NUMBER", "EMAIL_ADDRESS", "PERSON", "LOCATION"],
        )
        operators = {
            "PAN_NUMBER": OperatorConfig("custom", {"lambda": self.mask_pan}),
            "AADHAAR_NUMBER": OperatorConfig("custom", {"lambda": self.mask_aadhaar}),
            "PHONE_NUMBER": OperatorConfig("custom", {"lambda": self.mask_phone}),
            "EMAIL_ADDRESS": OperatorConfig("custom", {"lambda": self.mask_email}),
            "DEFAULT": OperatorConfig("replace", {"new_value": "<REDACTED>"}),
        }
        anonymized = self._anonymizer.anonymize(
            text=text, analyzer_results=analyzer_results, operators=operators
        )
        entity_types = sorted({r.entity_type for r in analyzer_results})
        result = PIIMaskingResult(
            original_field_count=len(analyzer_results),
            masked_field_count=len(analyzer_results),
            entities_detected=entity_types,
        )
        return anonymized.text, result

    # --- Data Residency ---

    @staticmethod
    def check_data_residency(endpoints: dict[str, str]) -> list[DataResidencyCheck]:
        india_patterns = ["ap-south", "india", "mumbai", "hyderabad", "chennai", "localhost", "127.0.0.1"]
        results = []
        for service, endpoint in endpoints.items():
            is_india = any(p in endpoint.lower() for p in india_patterns)
            results.append(DataResidencyCheck(
                service_name=service,
                endpoint=endpoint,
                region="ap-south-1" if is_india else "unknown",
                is_india_region=is_india,
            ))
        return results
