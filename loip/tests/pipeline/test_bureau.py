from loip.domains.risk_decisioning.processor import RiskDecisionProcessor
from loip.schemas.decision import Decision
from loip.tests.fixtures.factories import (
    make_application,
    make_clean_identity,
    make_clean_income,
    make_clean_affordability,
    make_clean_bureau,
    make_clean_fraud,
)
from loip.tests.fixtures.cibil_below_minimum import (
    BELOW_MINIMUM_SCORE,
    DPD_90_PLUS_SCORE,
    MARGINAL_SCORE,
)


def _decide(bureau, **income_overrides):
    processor = RiskDecisionProcessor(mock_mode=True)
    return processor.decide(
        make_application(),
        make_clean_identity(),
        make_clean_income(**income_overrides),
        make_clean_affordability(),
        bureau,
        make_clean_fraud(),
    )


def test_cibil_below_650_rejects():
    decision = _decide(make_clean_bureau(score=BELOW_MINIMUM_SCORE))
    assert decision.decision == Decision.REJECT
    assert any(c.code == "cibil_score_below_minimum" for c in decision.reason_codes)


def test_dpd_90_plus_rejects():
    decision = _decide(make_clean_bureau(score=DPD_90_PLUS_SCORE, dpd_90_plus=True))
    assert decision.decision == Decision.REJECT
    assert any(c.code == "dpd_90_plus_in_24_months" for c in decision.reason_codes)


def test_cibil_marginal_reviews():
    decision = _decide(make_clean_bureau(score=MARGINAL_SCORE))
    assert decision.decision == Decision.REVIEW
    assert any("cibil_marginal" in f for f in decision.review_flags)
