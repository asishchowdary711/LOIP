"""Shared factory helpers for building clean baseline domain results used across the Phase 1 DoD test suite."""

from schemas.affordability import AffordabilityResult
from schemas.bureau import CreditBureauResult
from schemas.decision import LoanApplication
from schemas.evidence import EvidenceChain, ReconciliationMethod
from schemas.fraud import FraudResult
from schemas.identity import IdentityVerificationResult
from schemas.income import IncomeResult


def make_application(**overrides) -> LoanApplication:
    kwargs = dict(
        application_id="DOD-TEST",
        applicant_name="Test Applicant",
        loan_amount=500000,
        tenure_months=36,
        employment_type="salaried",
        employment_tier=2,
        employer_name="Acme Corp",
    )
    kwargs.update(overrides)
    return LoanApplication(**kwargs)


def make_clean_identity(**overrides) -> IdentityVerificationResult:
    kwargs = dict(
        application_id="DOD-TEST",
        identity_confidence=1.0,
        pan_verified=True,
        aadhaar_verified=True,
    )
    kwargs.update(overrides)
    return IdentityVerificationResult(**kwargs)


def make_clean_income(**overrides) -> IncomeResult:
    kwargs = dict(
        application_id="DOD-TEST",
        segment="salaried",
        reconciled_annual_income=720000.0,
        verified_monthly_income=60000.0,
        income_confidence=0.85,
    )
    kwargs.update(overrides)
    return IncomeResult(**kwargs)


def make_clean_affordability(foir: float = 0.35, **overrides) -> AffordabilityResult:
    kwargs = dict(
        application_id="DOD-TEST",
        verified_monthly_income=60000.0,
        income_confidence=0.85,
        existing_obligations=0.0,
        proposed_emi=21000.0,
        total_obligations=21000.0,
        foir=foir,
        dti=foir,
        disposable_income=24000.0,
        liquidity_score=0.8,
        cashflow_stability=0.8,
        financial_stress_score=0.1,
        affordability_score=0.8,
        affordability_confidence=0.85,
    )
    kwargs.update(overrides)
    return AffordabilityResult(**kwargs)


def make_bureau_evidence(score: int) -> EvidenceChain:
    return EvidenceChain(
        claim=f"cibil_score={score}",
        supporting=[],
        reconciled_value=score,
        reconciliation_method=ReconciliationMethod.API_AUTHORITATIVE,
        confidence=1.0,
    )


def make_clean_bureau(**overrides) -> CreditBureauResult:
    score = overrides.pop("score", 750)
    kwargs = dict(
        application_id="DOD-TEST",
        bureau="cibil",
        score=score,
        active_loans=1,
        overdue_accounts=0,
        dpd_90_plus=False,
        total_outstanding=200000.0,
        enquiry_count_last_6m=1,
        evidence=make_bureau_evidence(score),
    )
    kwargs.update(overrides)
    return CreditBureauResult(**kwargs)


def make_clean_fraud(**overrides) -> FraudResult:
    kwargs = dict(application_id="DOD-TEST", fraud_score=0.0)
    kwargs.update(overrides)
    return FraudResult(**kwargs)
