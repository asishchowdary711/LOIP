"""Human review processor — queue management, case retrieval, override workflow."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from loip.domains.human_review.schemas import (
    OverrideDecision,
    OverrideRecord,
    OverrideRequest,
    ReviewCase,
    ReviewQueueFilters,
    ReviewQueueSummary,
    ReviewStatus,
)
from loip.schemas.decision import Decision, OnboardingDecision

logger = logging.getLogger(__name__)


class ReviewProcessor:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self._cases: dict[str, ReviewCase] = {}
        self._overrides: list[OverrideRecord] = []

    def create_review_case(self, decision: OnboardingDecision) -> ReviewCase:
        case_id = str(uuid.uuid4())
        primary_reason = decision.reason_codes[0].code if decision.reason_codes else None
        if not primary_reason and decision.review_flags:
            primary_reason = decision.review_flags[0]

        case = ReviewCase(
            case_id=case_id,
            application_id=decision.application_id,
            applicant_name=self._extract_applicant_name(decision),
            loan_amount=self._extract_loan_amount(decision),
            system_decision=decision.decision,
            risk_score=decision.risk_score,
            foir=decision.affordability_result.foir if decision.affordability_result else None,
            cibil_score=decision.bureau_result.score if decision.bureau_result else None,
            primary_reason_code=primary_reason,
            review_flags=decision.review_flags,
            onboarding_decision=decision,
        )
        self._cases[case_id] = case
        logger.info("Created review case %s for application %s", case_id, decision.application_id)
        return case

    def get_queue(self, filters: ReviewQueueFilters | None = None) -> list[ReviewCase]:
        if filters is None:
            filters = ReviewQueueFilters()

        cases = list(self._cases.values())

        if filters.status:
            cases = [c for c in cases if c.status == filters.status]
        if filters.assigned_to:
            cases = [c for c in cases if c.assigned_to == filters.assigned_to]
        if filters.min_risk_score is not None:
            cases = [c for c in cases if c.risk_score is not None and c.risk_score >= filters.min_risk_score]

        now = datetime.now(timezone.utc)
        for case in cases:
            created = case.created_at.replace(tzinfo=timezone.utc) if case.created_at.tzinfo is None else case.created_at
            case.age_in_queue_minutes = int((now - created).total_seconds() / 60)

        reverse = filters.sort_order == "desc"
        sort_key_map = {
            "risk_score": lambda c: c.risk_score or 0.0,
            "created_at": lambda c: c.created_at,
            "loan_amount": lambda c: c.loan_amount,
        }
        key_fn = sort_key_map.get(filters.sort_by, sort_key_map["risk_score"])
        cases.sort(key=key_fn, reverse=reverse)

        start = (filters.page - 1) * filters.page_size
        return cases[start : start + filters.page_size]

    def get_case(self, case_id: str) -> ReviewCase | None:
        return self._cases.get(case_id)

    def get_case_by_application(self, application_id: str) -> ReviewCase | None:
        for case in self._cases.values():
            if case.application_id == application_id:
                return case
        return None

    def assign_case(self, case_id: str, reviewer_id: str) -> ReviewCase | None:
        case = self._cases.get(case_id)
        if case is None:
            return None
        case.assigned_to = reviewer_id
        case.status = ReviewStatus.IN_PROGRESS
        case.updated_at = datetime.now(timezone.utc)
        return case

    def submit_override(self, case_id: str, request: OverrideRequest) -> OverrideRecord | None:
        case = self._cases.get(case_id)
        if case is None:
            return None

        feature_snapshot = self._build_feature_snapshot(case)

        override = OverrideRecord(
            override_id=str(uuid.uuid4()),
            case_id=case_id,
            application_id=case.application_id,
            original_decision=case.system_decision,
            override_decision=request.override_decision,
            reason_code=request.reason_code,
            notes=request.notes,
            reviewer_id=request.reviewer_id,
            feature_snapshot=feature_snapshot,
        )
        self._overrides.append(override)

        if request.override_decision == OverrideDecision.ESCALATE:
            case.status = ReviewStatus.ESCALATED
        else:
            case.status = ReviewStatus.COMPLETED
        case.updated_at = datetime.now(timezone.utc)

        logger.info(
            "Override submitted for case %s: %s -> %s by %s (reason: %s)",
            case_id,
            case.system_decision.value,
            request.override_decision.value,
            request.reviewer_id,
            request.reason_code.value,
        )
        return override

    def get_overrides(self, application_id: str | None = None) -> list[OverrideRecord]:
        if application_id:
            return [o for o in self._overrides if o.application_id == application_id]
        return list(self._overrides)

    def get_retraining_data(self) -> list[dict]:
        return [
            {
                "application_id": o.application_id,
                "original_decision": o.original_decision.value,
                "override_decision": o.override_decision.value,
                "reason_code": o.reason_code.value,
                "features": o.feature_snapshot,
                "overridden_at": o.overridden_at.isoformat(),
            }
            for o in self._overrides
            if o.feature_snapshot
        ]

    def get_queue_summary(self) -> ReviewQueueSummary:
        cases = list(self._cases.values())
        now = datetime.now(timezone.utc)
        pending = [c for c in cases if c.status == ReviewStatus.PENDING]
        ages = []
        for c in pending:
            created = c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at
            ages.append((now - created).total_seconds() / 60)

        return ReviewQueueSummary(
            total_pending=len(pending),
            total_in_progress=sum(1 for c in cases if c.status == ReviewStatus.IN_PROGRESS),
            total_completed=sum(1 for c in cases if c.status == ReviewStatus.COMPLETED),
            total_escalated=sum(1 for c in cases if c.status == ReviewStatus.ESCALATED),
            avg_age_minutes=sum(ages) / len(ages) if ages else 0.0,
        )

    def _extract_applicant_name(self, decision: OnboardingDecision) -> str:
        if decision.identity_result and decision.identity_result.entity_matches:
            for match in decision.identity_result.entity_matches:
                if match.field_name == "full_name" and match.sources:
                    return match.sources[0].normalized_value or match.sources[0].raw_value
        return decision.application_id

    def _extract_loan_amount(self, decision: OnboardingDecision) -> float:
        if decision.loan_amount is not None:
            return decision.loan_amount
        # Fallback for decisions created before loan_amount was carried through:
        # approximate from the proposed EMI (one year of payments).
        if decision.affordability_result:
            return decision.affordability_result.proposed_emi * 12
        return 0.0

    def _build_feature_snapshot(self, case: ReviewCase) -> dict:
        decision = case.onboarding_decision
        if decision is None:
            return {}
        snapshot = {
            "risk_score": decision.risk_score,
            "foir": decision.affordability_result.foir if decision.affordability_result else None,
            "identity_confidence": decision.identity_result.identity_confidence if decision.identity_result else None,
            "income_confidence": decision.income_result.income_confidence if decision.income_result else None,
            "verified_monthly_income": decision.income_result.verified_monthly_income if decision.income_result else None,
            "cibil_score": decision.bureau_result.score if decision.bureau_result else None,
            "cashflow_stability": decision.affordability_result.cashflow_stability if decision.affordability_result else None,
        }
        return {k: v for k, v in snapshot.items() if v is not None}
