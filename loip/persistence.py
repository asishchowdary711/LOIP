"""PostgreSQL persistence for onboarding decisions and the review workflow.

The review console keeps an in-memory queue for fast reads, but every decision
and override is written here so state survives restarts. On startup the queue is
rehydrated from these tables (see ``web/startup.py``).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime


def _utcnow_naive() -> datetime:
    """Naive UTC timestamp — the DB columns are ``timestamp without time zone``."""
    return datetime.utcnow()

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from loip.config import get_settings
from loip.domains.explainability.schemas import ExplainabilityResult
from loip.schemas.consent import ConsentPurpose, ConsentStatus
from loip.schemas.db_models import (
    ApplicationRecord,
    AuditLogRecord,
    Base,
    ConsentRecordDB,
    EvidenceRecord,
    ReviewOverrideRecord,
)
from loip.schemas.decision import OnboardingDecision

logger = logging.getLogger(__name__)

_engine = None
_sessionmaker = None

_STATUS_BY_DECISION = {"approve": "approved", "review": "in_review", "reject": "rejected"}


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def get_sessionmaker():
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def init_models() -> None:
    """Create tables if they don't exist (safety net; alembic is authoritative)."""
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def healthcheck() -> bool:
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Postgres healthcheck failed: %s", exc)
        return False


def _evidence_rows(application_id: str, decision: OnboardingDecision) -> list[EvidenceRecord]:
    rows = []
    for chain in decision.evidence_chains:
        rows.append(EvidenceRecord(
            application_id=application_id,
            claim=chain.claim,
            reconciled_value=str(chain.reconciled_value),
            reconciliation_method=chain.reconciliation_method.value,
            confidence=chain.confidence,
            supporting_json=[f.model_dump(mode="json") for f in chain.supporting],
            contradicting_json=[f.model_dump(mode="json") for f in chain.contradicting] or None,
        ))
    return rows


def _consent_row(application_id: str) -> ConsentRecordDB:
    return ConsentRecordDB(
        application_id=application_id,
        data_principal_id=f"DP-{application_id}",
        purpose=ConsentPurpose.CREDIT_BUREAU_PULL.value,
        consent_version="1.0",
        consented_at=_utcnow_naive(),
        status=ConsentStatus.ACTIVE.value,
        document_hash=hashlib.sha256(f"consent-{application_id}".encode()).hexdigest(),
        ip_address="127.0.0.1",
        user_agent="loip-web/1.0",
    )


async def save_decision(
    decision: OnboardingDecision,
    *,
    applicant_name: str,
    explainability: ExplainabilityResult | None = None,
    review_status: str = "pending",
) -> None:
    """Persist (or replace) an application decision + its evidence and consent."""
    app_id = decision.application_id
    sm = get_sessionmaker()
    async with sm() as session:
        async with session.begin():
            # Idempotent re-save: drop prior rows for this application.
            existing = await session.get(ApplicationRecord, app_id)
            if existing is not None:
                await session.delete(existing)
                await session.execute(delete(EvidenceRecord).where(EvidenceRecord.application_id == app_id))
                await session.execute(delete(ConsentRecordDB).where(ConsentRecordDB.application_id == app_id))
                await session.flush()

            session.add(ApplicationRecord(
                id=app_id,
                applicant_name=applicant_name,
                loan_amount=decision.loan_amount or 0.0,
                tenure_months=0,
                employment_type="",
                employment_tier=0,
                status=review_status,
                decided_at=decision.decided_at,
                decision=decision.decision.value,
                risk_score=decision.risk_score,
                reason_codes=[rc.model_dump(mode="json") for rc in decision.reason_codes] or None,
                review_flags=list(decision.review_flags) or None,
                decision_json=decision.model_dump(mode="json"),
                explainability_json=explainability.model_dump(mode="json") if explainability else None,
            ))
            for row in _evidence_rows(app_id, decision):
                session.add(row)
            session.add(_consent_row(app_id))
            session.add(AuditLogRecord(
                application_id=app_id,
                actor="onboarding_pipeline",
                action="onboarding_decision",
                detail={"decision": decision.decision.value, "risk_score": decision.risk_score},
            ))


async def load_decisions() -> list[dict]:
    """Return persisted decisions for queue rehydration, oldest first."""
    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            select(ApplicationRecord).order_by(ApplicationRecord.applied_at)
        )
        records = result.scalars().all()

    out = []
    for rec in records:
        if not rec.decision_json:
            continue
        decision = OnboardingDecision.model_validate(rec.decision_json)
        explainability = (
            ExplainabilityResult.model_validate(rec.explainability_json)
            if rec.explainability_json else None
        )
        out.append({
            "decision": decision,
            "explainability": explainability,
            "applicant_name": rec.applicant_name,
            "status": rec.status,
        })
    return out


async def save_override(
    application_id: str,
    *,
    reviewer_id: str,
    original_decision: str,
    override_decision: str,
    reason_code: str,
    notes: str | None,
    review_status: str,
) -> None:
    """Persist a reviewer override and update the application's review status."""
    sm = get_sessionmaker()
    async with sm() as session:
        async with session.begin():
            session.add(ReviewOverrideRecord(
                application_id=application_id,
                reviewer_id=reviewer_id,
                original_decision=original_decision,
                override_decision=override_decision,
                reason_code=reason_code,
                notes=notes,
            ))
            app = await session.get(ApplicationRecord, application_id)
            if app is not None:
                app.status = review_status
            session.add(AuditLogRecord(
                application_id=application_id,
                actor=reviewer_id,
                action="review_override",
                detail={
                    "original_decision": original_decision,
                    "override_decision": override_decision,
                    "reason_code": reason_code,
                },
            ))
