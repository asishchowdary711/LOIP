import pytest

from schemas.evidence import ReconciliationMethod
from loip.domains.identity_trust.processor import IdentityTrustProcessor
from loip.tests.fixtures.clean_salaried import EXTRACTED_FIELDS, APPLICATION_DATA
from integrations.cibil_client import CIBILClient
from integrations.base import ConsentRequiredError


@pytest.mark.asyncio
async def test_api_verified_fields_use_api_authoritative_method():
    processor = IdentityTrustProcessor(mock_mode=True)

    identity_result = await processor.verify_identity(
        "DOD-TEST", EXTRACTED_FIELDS, APPLICATION_DATA,
    )

    assert identity_result.api_results, "expected NSDL/UIDAI API results to be present"
    for api_result in identity_result.api_results:
        assert api_result.evidence is not None
        assert api_result.evidence.reconciliation_method == ReconciliationMethod.API_AUTHORITATIVE


@pytest.mark.asyncio
async def test_consent_required_before_bureau_pull():
    client = CIBILClient()
    client._mock = True

    with pytest.raises(ConsentRequiredError):
        await client.fetch_report(
            pan="ABCDE1234F",
            dob="01/01/1990",
            name="Rajesh Kumar",
            application_id="DOD-TEST",
            consent_verified=False,
        )


@pytest.mark.skip(
    reason="Requires MinIO document storage integration (Phase 2+); SourceLocation.document_id "
    "is not yet wired to real stored objects in mock mode."
)
def test_source_chains_trace_to_minio_documents():
    pass


@pytest.mark.xfail(
    reason="Genuine implementation gap: OnboardingDecision.evidence_chains and several "
    "sub-result evidence_chains lists are never populated by the current processors "
    "(mock_mode returns empty lists). Needs evidence-chain aggregation work in the "
    "risk decisioning / pipeline layer.",
    strict=True,
)
@pytest.mark.asyncio
async def test_every_output_field_has_evidence_chain():
    import numpy as np
    from schemas.decision import LoanApplication
    from loip.pipelines.onboarding import OnboardingPipeline

    pipeline = OnboardingPipeline(mock_mode=True)
    app = LoanApplication(
        application_id="TEST-TRACE",
        applicant_name="Rajesh Kumar",
        loan_amount=500000,
        tenure_months=36,
        employment_type="salaried",
        employment_tier=2,
        employer_name="Acme Corp",
    )
    images = [
        np.zeros((100, 100, 3), dtype=np.uint8),
        np.zeros((101, 101, 3), dtype=np.uint8),
        np.zeros((102, 102, 3), dtype=np.uint8),
        np.zeros((103, 103, 3), dtype=np.uint8),
    ]
    app_data = {
        "aadhaar_otp": "123456",
        "full_name": "Rajesh Kumar",
        "date_of_birth": "01/01/1990",
    }

    decision = await pipeline.execute(app, images, app_data)

    assert decision.evidence_chains
    assert decision.identity_result.evidence_chains
    assert decision.income_result.evidence_chains
    assert decision.affordability_result.evidence_chains
