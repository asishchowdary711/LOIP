"""Kafka domain-event pipeline integration test.

Gated on a reachable broker (the docker-compose stack); skipped otherwise so
the default suite stays green without infrastructure.
"""

from __future__ import annotations

import json
import uuid

import numpy as np
import pytest

from loip.config import get_settings
from loip.events import ALL_TOPICS, EventPublisher, Topic
from loip.pipelines.onboarding import OnboardingPipeline
from loip.schemas.decision import LoanApplication


async def _publisher_or_skip() -> EventPublisher:
    pub = EventPublisher()
    if not await pub.start():
        await pub.stop()
        pytest.skip("Kafka not reachable")
    return pub


@pytest.mark.asyncio
async def test_pipeline_publishes_domain_events():
    from aiokafka import AIOKafkaConsumer

    publisher = await _publisher_or_skip()
    app_id = f"PYTEST-EVT-{uuid.uuid4().hex[:8]}"

    try:
        pipeline = OnboardingPipeline(mock_mode=True)
        app = LoanApplication(
            application_id=app_id,
            applicant_name="Event Tester",
            loan_amount=2_000_000,  # forces a reject -> review.assigned + risk.decided
            tenure_months=12,
            employment_type="salaried",
            employment_tier=2,
            employer_name="Acme Corp",
        )
        images = [np.zeros((h, h, 3), dtype=np.uint8) for h in (100, 101, 102, 103)]
        app_data = {"aadhaar_otp": "123456", "full_name": "Mock User", "date_of_birth": "01/01/1990"}

        await pipeline.execute(app, images, app_data, event_publisher=publisher)
    finally:
        await publisher.stop()

    # Read everything and keep only events for this application.
    consumer = AIOKafkaConsumer(
        *ALL_TOPICS,
        bootstrap_servers=get_settings().kafka_bootstrap_servers,
        auto_offset_reset="earliest",
        group_id=f"pytest-{uuid.uuid4().hex[:8]}",
        enable_auto_commit=False,
    )
    await consumer.start()
    seen_topics: set[str] = set()
    try:
        for _ in range(10):
            batches = await consumer.getmany(timeout_ms=1000)
            for tp, messages in batches.items():
                for msg in messages:
                    payload = json.loads(msg.value)
                    if payload.get("application_id") == app_id:
                        seen_topics.add(tp.topic)
            if {Topic.RISK_DECIDED, Topic.DOCUMENT_CLASSIFIED}.issubset(seen_topics):
                break
    finally:
        await consumer.stop()

    assert Topic.DOCUMENT_CLASSIFIED in seen_topics
    assert Topic.IDENTITY_VERIFIED in seen_topics
    assert Topic.RISK_DECIDED in seen_topics
    assert Topic.REVIEW_ASSIGNED in seen_topics, "reject case should emit review.assigned"
