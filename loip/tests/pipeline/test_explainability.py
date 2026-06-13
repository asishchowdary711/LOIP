"""Phase 3 tests — explainability, copilot narrative, and human review override."""

import pytest

from loip.domains.explainability.copilot import ReviewerCopilot
from loip.domains.explainability.lime_explainer import LIMEExplainer
from loip.domains.explainability.processor import ExplainabilityProcessor
from loip.domains.explainability.schemas import ExplainabilityResult, SHAPExplanation
from loip.domains.explainability.shap_explainer import SHAPExplainer
from loip.domains.human_review.processor import ReviewProcessor
from loip.domains.human_review.schemas import (
    OverrideDecision,
    OverrideReasonCode,
    OverrideRequest,
    ReviewStatus,
)
from loip.schemas.affordability import AffordabilityResult
from loip.schemas.bureau import CreditBureauResult
from loip.schemas.decision import Decision, OnboardingDecision, ReasonCode
from loip.schemas.evidence import EvidenceChain, ExtractedField, ReconciliationMethod, SourceLocation, ExtractionMethod, DocumentType
from loip.schemas.fraud import FraudResult
from loip.schemas.identity import IdentityVerificationResult
from loip.schemas.income import IncomeResult


def _make_evidence_chain(claim: str = "test_claim") -> EvidenceChain:
    return EvidenceChain(
        claim=claim,
        supporting=[
            ExtractedField(
                field_name="test_field",
                raw_value="test",
                confidence=0.95,
                source=SourceLocation(
                    document_id="doc-001",
                    document_type=DocumentType.PAN,
                    extraction_method=ExtractionMethod.PADDLEOCR,
                    model_version="paddleocr-4.0",
                ),
            )
        ],
        reconciled_value="test",
        reconciliation_method=ReconciliationMethod.HIGHEST_CONFIDENCE,
        confidence=0.95,
    )


def _make_decision(
    decision: Decision = Decision.REVIEW,
    risk_score: float = 0.55,
    foir: float = 0.52,
    cibil: int = 710,
) -> OnboardingDecision:
    evidence = _make_evidence_chain()
    return OnboardingDecision(
        application_id="APP-TEST-001",
        decision=decision,
        review_flags=["foir_marginal:0.52"] if decision == Decision.REVIEW else [],
        reason_codes=[ReasonCode(code="foir_marginal", category="affordability")] if decision == Decision.REVIEW else [],
        risk_score=risk_score,
        identity_result=IdentityVerificationResult(
            application_id="APP-TEST-001",
            identity_confidence=0.85,
            pan_verified=True,
            aadhaar_verified=True,
        ),
        income_result=IncomeResult(
            application_id="APP-TEST-001",
            segment="salaried",
            reconciled_annual_income=720000,
            verified_monthly_income=60000,
            income_confidence=0.80,
        ),
        affordability_result=AffordabilityResult(
            application_id="APP-TEST-001",
            verified_monthly_income=60000,
            income_confidence=0.80,
            existing_obligations=12000,
            proposed_emi=19200,
            total_obligations=31200,
            foir=foir,
            dti=foir,
            disposable_income=13800,
            liquidity_score=0.65,
            cashflow_stability=0.78,
            financial_stress_score=0.10,
            affordability_score=0.72,
            affordability_confidence=0.80,
        ),
        bureau_result=CreditBureauResult(
            application_id="APP-TEST-001",
            bureau="cibil",
            score=cibil,
            active_loans=2,
            overdue_accounts=0,
            dpd_90_plus=False,
            total_outstanding=350000,
            enquiry_count_last_6m=2,
            evidence=evidence,
        ),
        evidence_chains=[evidence],
    )


RISK_FEATURES = {
    "identity_confidence": 0.85,
    "income_confidence": 0.80,
    "foir": 0.52,
    "cibil_score_normalized": 0.683,
    "cashflow_stability": 0.78,
    "employment_tier": 2,
    "loan_to_income_ratio": 0.42,
}


class TestSHAPExplainer:
    def test_mock_shap_returns_explanation(self):
        explainer = SHAPExplainer(mock_mode=True)
        result = explainer.explain("risk_xgboost", RISK_FEATURES)

        assert isinstance(result, SHAPExplanation)
        assert result.model_name == "risk_xgboost"
        assert result.base_value == 0.5
        assert len(result.all_shap_values) == len(RISK_FEATURES)

    def test_shap_top_contributors_capped_at_3(self):
        explainer = SHAPExplainer(mock_mode=True)
        result = explainer.explain("risk_xgboost", RISK_FEATURES)

        assert len(result.top_positive) <= 3
        assert len(result.top_negative) <= 3

    def test_shap_contributors_have_direction(self):
        explainer = SHAPExplainer(mock_mode=True)
        result = explainer.explain("risk_xgboost", RISK_FEATURES)

        for c in result.top_positive:
            assert c.direction == "positive"
            assert c.shap_value > 0
        for c in result.top_negative:
            assert c.direction == "negative"
            assert c.shap_value < 0


class TestLIMEExplainer:
    def test_mock_lime_returns_attributions(self):
        explainer = LIMEExplainer(mock_mode=True)
        tokens = [
            {"text": "RAJESH", "bbox": {"x0": 100, "y0": 50, "x1": 200, "y1": 70}},
            {"text": "KUMAR", "bbox": {"x0": 210, "y0": 50, "x1": 300, "y1": 70}},
            {"text": "DOB:", "bbox": {"x0": 100, "y0": 80, "x1": 150, "y1": 100}},
        ]
        result = explainer.explain_extraction(
            document_id="doc-001",
            document_type="pan",
            field_name="full_name",
            extracted_value="RAJESH KUMAR",
            ocr_tokens=tokens,
            confidence=0.92,
        )

        assert result.document_id == "doc-001"
        assert result.field_name == "full_name"
        assert len(result.attributions) > 0
        assert result.prediction_confidence == 0.92

    def test_lime_matching_tokens_have_high_weight(self):
        explainer = LIMEExplainer(mock_mode=True)
        tokens = [
            {"text": "RAJESH", "bbox": {}},
            {"text": "KUMAR", "bbox": {}},
            {"text": "OTHER", "bbox": {}},
        ]
        result = explainer.explain_extraction(
            document_id="doc-001",
            document_type="pan",
            field_name="full_name",
            extracted_value="RAJESH KUMAR",
            ocr_tokens=tokens,
            confidence=0.90,
        )

        matched = [a for a in result.attributions if a.token in ("RAJESH", "KUMAR")]
        unmatched = [a for a in result.attributions if a.token == "OTHER"]
        assert all(a.weight > 0.5 for a in matched)
        assert all(a.weight < 0 for a in unmatched)


class TestReviewerCopilot:
    @pytest.mark.asyncio
    async def test_mock_copilot_generates_narrative(self):
        copilot = ReviewerCopilot(mock_mode=True)
        case_data = {
            "application": {
                "applicant_name": "Rajesh Kumar",
                "loan_amount": 500000,
                "tenure_months": 36,
                "employment_type": "salaried",
                "employment_tier": 2,
                "employer_name": "Infosys Ltd",
            },
            "identity": {"identity_confidence": 0.85, "pan_verified": True, "aadhaar_verified": True, "tamper_flags": []},
            "income": {"verified_monthly_income": 60000, "income_confidence": 0.80, "anomaly_flags": []},
            "affordability": {"foir": 0.52, "existing_obligations": 12000, "proposed_emi": 19200, "disposable_income": 13800, "cashflow_stability": 0.78},
            "bureau": {"score": 710, "active_loans": 2, "overdue_accounts": 0},
            "decision": {"decision": "review", "reason_codes": [{"code": "foir_marginal"}], "review_flags": ["foir_marginal:0.52"]},
        }
        result = await copilot.generate_narrative(case_data)

        assert "Rajesh Kumar" in result.profile_summary
        assert result.primary_decision_reason
        assert len(result.reviewer_questions) == 2
        assert "mock" in result.model_id

    @pytest.mark.asyncio
    async def test_copilot_flags_inconsistencies_on_high_foir(self):
        copilot = ReviewerCopilot(mock_mode=True)
        case_data = {
            "application": {"applicant_name": "Test User", "loan_amount": 300000, "tenure_months": 24, "employment_type": "salaried", "employment_tier": 3, "employer_name": "ABC Corp"},
            "identity": {"identity_confidence": 0.85, "pan_verified": True, "aadhaar_verified": True, "tamper_flags": []},
            "income": {"verified_monthly_income": 45000, "income_confidence": 0.75, "anomaly_flags": []},
            "affordability": {"foir": 0.58, "existing_obligations": 10000, "proposed_emi": 16100, "disposable_income": 3900, "cashflow_stability": 0.60},
            "bureau": {"score": 720, "active_loans": 1, "overdue_accounts": 0},
            "decision": {"decision": "review", "reason_codes": [], "review_flags": ["foir_marginal:0.58"]},
        }
        result = await copilot.generate_narrative(case_data)

        foir_mentioned = any("FOIR" in inc or "foir" in inc.lower() for inc in result.inconsistencies)
        assert foir_mentioned


class TestExplainabilityProcessor:
    @pytest.mark.asyncio
    async def test_full_explainability_output(self):
        processor = ExplainabilityProcessor(mock_mode=True)
        case_data = {
            "application": {"applicant_name": "Test", "loan_amount": 500000, "tenure_months": 36, "employment_type": "salaried", "employment_tier": 2, "employer_name": "Test Corp"},
            "identity": {"identity_confidence": 0.85, "pan_verified": True, "aadhaar_verified": True, "tamper_flags": []},
            "income": {"verified_monthly_income": 60000, "income_confidence": 0.80, "anomaly_flags": []},
            "affordability": {"foir": 0.45, "existing_obligations": 10000, "proposed_emi": 17000, "disposable_income": 18000, "cashflow_stability": 0.82},
            "bureau": {"score": 750, "active_loans": 1, "overdue_accounts": 0},
            "decision": {"decision": "approve", "reason_codes": [], "review_flags": []},
        }
        result = await processor.explain(
            application_id="APP-001",
            risk_features=RISK_FEATURES,
            case_data=case_data,
        )

        assert isinstance(result, ExplainabilityResult)
        assert result.application_id == "APP-001"
        assert len(result.shap_explanations) >= 1
        assert result.copilot is not None
        assert len(result.risk_factors) > 0

    @pytest.mark.asyncio
    async def test_risk_factors_populated_in_decision(self):
        processor = ExplainabilityProcessor(mock_mode=True)
        result = await processor.explain(
            application_id="APP-002",
            risk_features=RISK_FEATURES,
        )

        assert len(result.risk_factors) > 0
        assert any("+" in f or "-" in f for f in result.risk_factors)


class TestHumanReviewOverride:
    def test_create_review_case(self):
        processor = ReviewProcessor(mock_mode=True)
        decision = _make_decision(Decision.REVIEW)
        case = processor.create_review_case(decision)

        assert case.application_id == "APP-TEST-001"
        assert case.system_decision == Decision.REVIEW
        assert case.status == ReviewStatus.PENDING

    def test_override_changes_status_to_completed(self):
        processor = ReviewProcessor(mock_mode=True)
        decision = _make_decision(Decision.REVIEW)
        case = processor.create_review_case(decision)

        override = processor.submit_override(
            case.case_id,
            OverrideRequest(
                reviewer_id="reviewer_01",
                override_decision=OverrideDecision.APPROVE,
                reason_code=OverrideReasonCode.INCOME_VERIFIED_MANUALLY,
                notes="Verified salary slips with employer HR directly via phone call.",
            ),
        )

        assert override is not None
        assert override.original_decision == Decision.REVIEW
        assert override.override_decision == OverrideDecision.APPROVE
        updated_case = processor.get_case(case.case_id)
        assert updated_case.status == ReviewStatus.COMPLETED

    def test_escalate_sets_escalated_status(self):
        processor = ReviewProcessor(mock_mode=True)
        decision = _make_decision(Decision.REVIEW)
        case = processor.create_review_case(decision)

        processor.submit_override(
            case.case_id,
            OverrideRequest(
                reviewer_id="reviewer_01",
                override_decision=OverrideDecision.ESCALATE,
                reason_code=OverrideReasonCode.POLICY_EXCEPTION,
                notes="Requires senior reviewer approval due to policy exception request.",
            ),
        )

        updated_case = processor.get_case(case.case_id)
        assert updated_case.status == ReviewStatus.ESCALATED

    def test_override_stores_feature_snapshot_for_retraining(self):
        processor = ReviewProcessor(mock_mode=True)
        decision = _make_decision(Decision.REVIEW, foir=0.55, cibil=690)
        case = processor.create_review_case(decision)

        processor.submit_override(
            case.case_id,
            OverrideRequest(
                reviewer_id="reviewer_01",
                override_decision=OverrideDecision.APPROVE,
                reason_code=OverrideReasonCode.INCOME_VERIFIED_MANUALLY,
                notes="Income verified through alternative documents — ITR matched bank credits.",
            ),
        )

        retraining = processor.get_retraining_data()
        assert len(retraining) == 1
        assert retraining[0]["original_decision"] == "review"
        assert retraining[0]["override_decision"] == "approve"
        assert "foir" in retraining[0]["features"]
        assert "cibil_score" in retraining[0]["features"]

    def test_queue_sorted_by_risk_score_descending(self):
        processor = ReviewProcessor(mock_mode=True)
        for score in [0.3, 0.8, 0.5]:
            d = _make_decision(Decision.REVIEW, risk_score=score)
            d.application_id = f"APP-{score}"
            processor.create_review_case(d)

        queue = processor.get_queue()
        scores = [c.risk_score for c in queue]
        assert scores == sorted(scores, reverse=True)

    def test_queue_summary_counts(self):
        processor = ReviewProcessor(mock_mode=True)
        for _ in range(3):
            processor.create_review_case(_make_decision(Decision.REVIEW))

        summary = processor.get_queue_summary()
        assert summary.total_pending == 3
        assert summary.total_in_progress == 0
