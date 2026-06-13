import pytest
import numpy as np
from schemas.decision import LoanApplication, Decision
from loip.pipelines.onboarding import OnboardingPipeline

@pytest.mark.asyncio
async def test_clean_salaried_application_approves():
    pipeline = OnboardingPipeline(mock_mode=True)
    app = LoanApplication(
        application_id="TEST-123",
        applicant_name="Mock User",
        loan_amount=500000,
        tenure_months=36,
        employment_type="salaried",
        employment_tier=2,
        employer_name="Acme Corp"
    )
    
    images = [
        np.zeros((100, 100, 3), dtype=np.uint8), # PAN
        np.zeros((101, 101, 3), dtype=np.uint8), # AADHAAR
        np.zeros((102, 102, 3), dtype=np.uint8), # SALARY_SLIP
        np.zeros((103, 103, 3), dtype=np.uint8)  # SELFIE
    ]
    app_data = {
        "aadhaar_otp": "123456",
        "full_name": "Mock User",
        "date_of_birth": "01/01/1990"
    }
    
    decision = await pipeline.execute(app, images, app_data)
    
    assert decision.decision == Decision.APPROVE
    assert decision.application_id == "TEST-123"

@pytest.mark.asyncio
async def test_foir_above_60_rejects():
    pipeline = OnboardingPipeline(mock_mode=True)
    app = LoanApplication(
        application_id="TEST-124",
        applicant_name="Mock User",
        loan_amount=5000000,
        tenure_months=12,
        employment_type="salaried",
        employment_tier=2
    )
    
    images = [
        np.zeros((100, 100, 3), dtype=np.uint8), # PAN
        np.zeros((101, 101, 3), dtype=np.uint8), # AADHAAR
        np.zeros((102, 102, 3), dtype=np.uint8), # SALARY_SLIP
        np.zeros((103, 103, 3), dtype=np.uint8)  # SELFIE
    ]
    app_data = {
        "aadhaar_otp": "123456",
        "full_name": "Mock User",
        "date_of_birth": "01/01/1990"
    }
    
    decision = await pipeline.execute(app, images, app_data)
    
    assert decision.decision == Decision.REJECT
    assert any(code.code == "foir_exceeded" for code in decision.reason_codes)
