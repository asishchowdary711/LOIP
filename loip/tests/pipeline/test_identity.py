import pytest

from schemas.identity import APIVerificationResult, IdentityFlag
from schemas.evidence import EvidenceChain, ReconciliationMethod
from schemas.decision import Decision
from loip.domains.identity_trust.processor import IdentityTrustProcessor
from loip.domains.risk_decisioning.processor import RiskDecisionProcessor
from loip.tests.fixtures.factories import (
    make_application,
    make_clean_income,
    make_clean_affordability,
    make_clean_bureau,
    make_clean_fraud,
)
from loip.tests.fixtures.identity_mismatch_pan_aadhaar import (
    EXTRACTED_FIELDS,
    APPLICATION_DATA_NAME_MISMATCH,
    APPLICATION_DATA_DOB_MISMATCH,
)
from loip.tests.fixtures.forged_document_metadata import (
    EXTRACTED_FIELDS as FORGED_EXTRACTED_FIELDS,
    APPLICATION_DATA as FORGED_APPLICATION_DATA,
    DOCUMENT_METADATA,
)


def _decide_with_identity(identity_result):
    processor = RiskDecisionProcessor(mock_mode=True)
    return processor.decide(
        make_application(),
        identity_result,
        make_clean_income(),
        make_clean_affordability(),
        make_clean_bureau(),
        make_clean_fraud(),
    )


@pytest.mark.asyncio
async def test_pan_nsdl_inactive_rejects(monkeypatch):
    processor = IdentityTrustProcessor(mock_mode=True)

    async def inactive_pan(*args, **kwargs):
        return APIVerificationResult(
            source="nsdl_api", matched=False, status="inactive",
            evidence=EvidenceChain(
                claim="pan_verified=ABCDE1234F", supporting=[], reconciled_value="ABCDE1234F",
                reconciliation_method=ReconciliationMethod.API_AUTHORITATIVE, confidence=1.0,
            ),
        )
    monkeypatch.setattr(processor.nsdl_client, "verify_pan", inactive_pan)

    identity_result = await processor.verify_identity(
        "DOD-TEST",
        {
            "pan_number": "ABCDE1234F", "full_name": "Rajesh Kumar", "date_of_birth": "01/01/1990",
            "aadhaar_number": "123456789012",
        },
        {"aadhaar_otp": "123456", "full_name": "Rajesh Kumar", "date_of_birth": "01/01/1990"},
    )

    assert identity_result.has_flag(IdentityFlag.PAN_NSDL_INACTIVE)

    decision = _decide_with_identity(identity_result)
    assert decision.decision == Decision.REJECT
    assert any(c.code == "pan_inactive_or_invalid" for c in decision.reason_codes)


@pytest.mark.asyncio
async def test_aadhaar_otp_failure_rejects(monkeypatch):
    processor = IdentityTrustProcessor(mock_mode=True)

    async def failed_otp(*args, **kwargs):
        return APIVerificationResult(
            source="uidai_api", matched=False, status="otp_failed",
            evidence=EvidenceChain(
                claim="aadhaar_verified", supporting=[], reconciled_value="False",
                reconciliation_method=ReconciliationMethod.API_AUTHORITATIVE, confidence=0.0,
            ),
        )
    monkeypatch.setattr(processor.uidai_client, "verify_otp", failed_otp)

    identity_result = await processor.verify_identity(
        "DOD-TEST",
        {
            "pan_number": "ABCDE1234F", "full_name": "Rajesh Kumar", "date_of_birth": "01/01/1990",
            "aadhaar_number": "123456789012",
        },
        {"aadhaar_otp": "000000", "full_name": "Rajesh Kumar", "date_of_birth": "01/01/1990"},
    )

    assert identity_result.has_flag(IdentityFlag.AADHAAR_OTP_FAILED)

    decision = _decide_with_identity(identity_result)
    assert decision.decision == Decision.REJECT
    assert any(c.code == "aadhaar_verification_failed" for c in decision.reason_codes)


@pytest.mark.asyncio
async def test_name_mismatch_pan_aadhaar_rejects():
    processor = IdentityTrustProcessor(mock_mode=True)

    identity_result = await processor.verify_identity(
        "DOD-TEST", EXTRACTED_FIELDS, APPLICATION_DATA_NAME_MISMATCH,
    )

    assert identity_result.has_flag(IdentityFlag.NAME_PAN_AADHAAR_MISMATCH)

    decision = _decide_with_identity(identity_result)
    assert decision.decision == Decision.REJECT
    assert any(c.code == "identity_mismatch_name" for c in decision.reason_codes)


@pytest.mark.asyncio
async def test_dob_mismatch_rejects():
    processor = IdentityTrustProcessor(mock_mode=True)

    identity_result = await processor.verify_identity(
        "DOD-TEST", EXTRACTED_FIELDS, APPLICATION_DATA_DOB_MISMATCH,
    )

    assert identity_result.has_flag(IdentityFlag.DOB_MISMATCH)

    decision = _decide_with_identity(identity_result)
    assert decision.decision == Decision.REJECT
    assert any(c.code == "identity_mismatch_dob" for c in decision.reason_codes)


@pytest.mark.asyncio
async def test_forged_document_metadata_flags():
    processor = IdentityTrustProcessor(mock_mode=True)

    identity_result = await processor.verify_identity(
        "DOD-TEST", FORGED_EXTRACTED_FIELDS, FORGED_APPLICATION_DATA,
        document_metadata=DOCUMENT_METADATA,
    )

    assert identity_result.has_flag(IdentityFlag.DOCUMENT_METADATA_ANOMALY)
