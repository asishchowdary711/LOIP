from loip.domains.income_intel.processor import IncomeIntelligenceProcessor
from loip.domains.risk_decisioning.processor import RiskDecisionProcessor
from loip.schemas.income import IncomeFlag
from loip.schemas.decision import Decision
from loip.tests.fixtures.factories import (
    make_application,
    make_clean_identity,
    make_clean_affordability,
    make_clean_bureau,
    make_clean_fraud,
)
from loip.tests.fixtures.income_mismatch_salary_vs_bank import EXTRACTED_DATA as MISMATCH_DATA
from loip.tests.fixtures.income_inflated import EXTRACTED_DATA as INFLATED_DATA
from loip.tests.fixtures.no_salary_credit_found import EXTRACTED_DATA as NO_CREDIT_DATA
from loip.tests.fixtures.employer_name_mismatch import (
    EXTRACTED_DATA as EMPLOYER_MISMATCH_DATA,
    APPLICATION_EMPLOYER_NAME,
)


def test_salary_slip_vs_bank_mismatch_flags():
    processor = IncomeIntelligenceProcessor(mock_mode=True)
    result = processor.process_income("DOD-TEST", MISMATCH_DATA, segment="salaried")
    assert IncomeFlag.SALARY_SLIP_VS_BANK_MISMATCH in result.anomaly_flags


def test_income_inflation_reviews():
    income_processor = IncomeIntelligenceProcessor(mock_mode=True)
    income_result = income_processor.process_income("DOD-TEST", INFLATED_DATA, segment="salaried")
    assert IncomeFlag.INCOME_INFLATION in income_result.anomaly_flags

    affordability = make_clean_affordability(
        foir=0.18, verified_monthly_income=income_result.verified_monthly_income,
    )
    decision_processor = RiskDecisionProcessor(mock_mode=True)
    decision = decision_processor.decide(
        make_application(), make_clean_identity(), income_result, affordability,
        make_clean_bureau(), make_clean_fraud(),
    )

    assert decision.decision == Decision.REVIEW
    assert any("income_inflation" in f for f in decision.review_flags)


def test_no_salary_credits_in_bank_rejects():
    income_processor = IncomeIntelligenceProcessor(mock_mode=True)
    income_result = income_processor.process_income("DOD-TEST", NO_CREDIT_DATA, segment="salaried")
    assert IncomeFlag.NO_SALARY_CREDIT_FOUND in income_result.anomaly_flags

    decision_processor = RiskDecisionProcessor(mock_mode=True)
    decision = decision_processor.decide(
        make_application(), make_clean_identity(), income_result, make_clean_affordability(),
        make_clean_bureau(), make_clean_fraud(),
    )

    assert decision.decision == Decision.REJECT
    assert any(c.code == "bank_credit_not_found" for c in decision.reason_codes)


def test_employer_name_mismatch_flags():
    processor = IncomeIntelligenceProcessor(mock_mode=True)
    result = processor.process_income(
        "DOD-TEST", EMPLOYER_MISMATCH_DATA, segment="salaried",
        application_employer_name=APPLICATION_EMPLOYER_NAME,
    )
    assert IncomeFlag.EMPLOYER_NAME_MISMATCH in result.anomaly_flags
