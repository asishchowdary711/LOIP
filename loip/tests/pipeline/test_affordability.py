from loip.domains.affordability.processor import AffordabilityProcessor
from loip.domains.risk_decisioning.processor import RiskDecisionProcessor
from loip.schemas.affordability import AffordabilityFlag
from loip.schemas.decision import Decision
from loip.tests.fixtures.factories import (
    make_application,
    make_clean_identity,
    make_clean_income,
    make_clean_bureau,
    make_clean_fraud,
)
from loip.tests.fixtures.foir_exceeded import MARGINAL_LOAN_AMOUNT, MARGINAL_TENURE_MONTHS


def test_foir_50_to_60_reviews():
    affordability_processor = AffordabilityProcessor(mock_mode=True)
    income_result = {"verified_monthly_income": 60000.0, "income_confidence": 0.85}
    application_data = {"loan_amount": MARGINAL_LOAN_AMOUNT, "tenure_months": MARGINAL_TENURE_MONTHS}

    affordability = affordability_processor.process_affordability(
        "DOD-TEST", income_result, application_data, extracted_data={}
    )

    assert 0.50 < affordability.foir <= 0.60
    assert AffordabilityFlag.FOIR_MARGINAL in affordability.anomaly_flags

    decision_processor = RiskDecisionProcessor(mock_mode=True)
    decision = decision_processor.decide(
        make_application(loan_amount=MARGINAL_LOAN_AMOUNT, tenure_months=MARGINAL_TENURE_MONTHS),
        make_clean_identity(),
        make_clean_income(verified_monthly_income=60000.0),
        affordability,
        make_clean_bureau(),
        make_clean_fraud(),
    )

    assert decision.decision == Decision.REVIEW
    assert any("foir_marginal" in f for f in decision.review_flags)
