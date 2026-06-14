"""V-CIP disbursal gate in the risk decision engine (RBI Jan 2020 circular)."""

from datetime import UTC, datetime

from loip.domains.identity_trust.vcip import VCIP_REQUIRED_ABOVE
from loip.domains.risk_decisioning.processor import RiskDecisionProcessor
from loip.schemas.decision import Decision
from loip.schemas.vcip import VCIPFlag, VCIPResult, VCIPStatus
from loip.tests.fixtures.factories import (
    make_application,
    make_clean_affordability,
    make_clean_bureau,
    make_clean_fraud,
    make_clean_identity,
    make_clean_income,
)

# Above the V-CIP ceiling so the gate is in play.
HIGH_AMOUNT = VCIP_REQUIRED_ABOVE + 300_000
LOW_AMOUNT = VCIP_REQUIRED_ABOVE - 50_000


def _decide(loan_amount, vcip=None):
    proc = RiskDecisionProcessor(mock_mode=True)
    return proc.decide(
        make_application(loan_amount=loan_amount),
        make_clean_identity(),
        make_clean_income(),
        make_clean_affordability(),
        make_clean_bureau(),
        make_clean_fraud(),
        vcip=vcip,
    )


def _vcip(status: VCIPStatus, flags=None) -> VCIPResult:
    return VCIPResult(
        session_id="s1",
        application_id="DOD-TEST",
        status=status,
        passed=status == VCIPStatus.COMPLETED,
        flags=flags or [],
        completed_at=datetime.now(UTC),
    )


def test_below_threshold_approves_without_vcip():
    decision = _decide(LOW_AMOUNT, vcip=None)
    assert decision.decision == Decision.APPROVE
    assert decision.disbursal_blocked is False


def test_high_amount_without_vcip_blocks_disbursal():
    decision = _decide(HIGH_AMOUNT, vcip=None)
    assert decision.decision == Decision.REVIEW
    assert decision.disbursal_blocked is True
    assert decision.disbursal_block_reason == "vcip_required_not_completed"
    assert "vcip_pending" in decision.review_flags


def test_high_amount_with_completed_vcip_approves():
    decision = _decide(HIGH_AMOUNT, vcip=_vcip(VCIPStatus.COMPLETED))
    assert decision.decision == Decision.APPROVE
    assert decision.disbursal_blocked is False


def test_failed_vcip_rejects():
    decision = _decide(HIGH_AMOUNT, vcip=_vcip(VCIPStatus.FAILED, [VCIPFlag.GEOTAG_OUTSIDE_INDIA]))
    assert decision.decision == Decision.REJECT
    assert any(rc.code == "vcip_failed" for rc in decision.reason_codes)
