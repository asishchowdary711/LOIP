"""Postgres persistence integration tests.

Gated on a reachable database (the docker-compose stack); skipped otherwise so
the default suite stays green without infrastructure.
"""

from __future__ import annotations

import numpy as np
import pytest

from loip import persistence
from loip.pipelines.onboarding import OnboardingPipeline
from loip.schemas.decision import LoanApplication
from loip.schemas.db_models import ApplicationRecord, EvidenceRecord, ReviewOverrideRecord

TEST_APP_ID = "PYTEST-PERSIST-1"


@pytest.fixture(autouse=True)
def _reset_engine():
    """pytest-asyncio uses a fresh event loop per test; the module-level async
    engine is bound to the loop it was created in, so reset it each test."""
    persistence._engine = None
    persistence._sessionmaker = None
    yield
    persistence._engine = None
    persistence._sessionmaker = None


async def _pg_or_skip():
    await persistence.init_models()
    if not await persistence.healthcheck():
        pytest.skip("Postgres not reachable")


async def _make_decision():
    pipeline = OnboardingPipeline(mock_mode=True)
    app = LoanApplication(
        application_id=TEST_APP_ID,
        applicant_name="Persist Tester",
        loan_amount=600000,
        tenure_months=36,
        employment_type="salaried",
        employment_tier=2,
        employer_name="Acme Corp",
    )
    images = [np.zeros((h, h, 3), dtype=np.uint8) for h in (100, 101, 102, 103)]
    app_data = {"aadhaar_otp": "123456", "full_name": "Mock User", "date_of_birth": "01/01/1990"}
    return await pipeline.execute(app, images, app_data)


async def _cleanup():
    sm = persistence.get_sessionmaker()
    async with sm() as session:
        async with session.begin():
            from sqlalchemy import delete

            await session.execute(delete(EvidenceRecord).where(EvidenceRecord.application_id == TEST_APP_ID))
            await session.execute(delete(ReviewOverrideRecord).where(ReviewOverrideRecord.application_id == TEST_APP_ID))
            obj = await session.get(ApplicationRecord, TEST_APP_ID)
            if obj is not None:
                await session.delete(obj)


@pytest.mark.asyncio
async def test_decision_roundtrips_through_postgres():
    await _pg_or_skip()
    try:
        decision = await _make_decision()
        await persistence.save_decision(decision, applicant_name="Persist Tester", review_status="pending")

        rows = await persistence.load_decisions()
        match = next((r for r in rows if r["decision"].application_id == TEST_APP_ID), None)
        assert match is not None, "saved decision not found on reload"
        assert match["applicant_name"] == "Persist Tester"
        assert match["status"] == "pending"
        # Full decision rehydrated with nested results intact.
        assert match["decision"].loan_amount == 600000
        assert match["decision"].income_result is not None
        assert match["decision"].evidence_chains
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_override_persists_and_updates_status():
    await _pg_or_skip()
    try:
        decision = await _make_decision()
        await persistence.save_decision(decision, applicant_name="Persist Tester", review_status="pending")

        await persistence.save_override(
            TEST_APP_ID,
            reviewer_id="reviewer_test",
            original_decision=decision.decision.value,
            override_decision="approve",
            reason_code="policy_exception",
            notes="integration test override",
            review_status="completed",
        )

        rows = await persistence.load_decisions()
        match = next((r for r in rows if r["decision"].application_id == TEST_APP_ID), None)
        assert match is not None
        assert match["status"] == "completed", "override should update application status"

        sm = persistence.get_sessionmaker()
        async with sm() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(ReviewOverrideRecord).where(ReviewOverrideRecord.application_id == TEST_APP_ID)
            )
            overrides = result.scalars().all()
        assert len(overrides) == 1
        assert overrides[0].override_decision == "approve"
    finally:
        await _cleanup()
