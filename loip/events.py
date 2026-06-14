"""Kafka domain-event pipeline.

As the onboarding pipeline runs, each domain emits an event to its Kafka topic
(the topics created by ``kafka-init`` in docker-compose.yml). Publishing is
best-effort: if Kafka is unreachable the publisher no-ops with a warning, so
the pipeline and the web app keep working without the broker.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from loip.config import get_settings

logger = logging.getLogger(__name__)


class Topic:
    DOCUMENT_CLASSIFIED = "document.classified"
    IDENTITY_VERIFIED = "identity.verified"
    INCOME_RECONCILED = "income.reconciled"
    AFFORDABILITY_COMPUTED = "affordability.computed"
    FRAUD_SCORED = "fraud.scored"
    RISK_DECIDED = "risk.decided"
    REVIEW_ASSIGNED = "review.assigned"
    CONSENT_CAPTURED = "consent.captured"


ALL_TOPICS = [
    Topic.DOCUMENT_CLASSIFIED, Topic.IDENTITY_VERIFIED, Topic.INCOME_RECONCILED,
    Topic.AFFORDABILITY_COMPUTED, Topic.FRAUD_SCORED, Topic.RISK_DECIDED,
    Topic.REVIEW_ASSIGNED, Topic.CONSENT_CAPTURED,
]


def _serialize(payload: dict[str, Any]) -> bytes:
    enriched = {"emitted_at": datetime.utcnow().isoformat(), **payload}
    return json.dumps(enriched, default=str).encode("utf-8")


class EventPublisher:
    """Thin async wrapper over an aiokafka producer with graceful degradation."""

    def __init__(self, bootstrap_servers: str | None = None):
        self.bootstrap_servers = bootstrap_servers or get_settings().kafka_bootstrap_servers
        self._producer = None
        self._ready = False

    async def start(self) -> bool:
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
            await self._producer.start()
            self._ready = True
            logger.info("Kafka event publisher connected to %s", self.bootstrap_servers)
        except Exception as exc:  # noqa: BLE001
            self._ready = False
            self._producer = None
            logger.warning("Kafka unavailable (%s); domain events will not be published", exc)
        return self._ready

    async def stop(self) -> None:
        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception:  # noqa: BLE001
                pass
            self._producer = None
            self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    async def publish(self, topic: str, key: str, payload: dict[str, Any]) -> bool:
        """Publish one event. Returns False (no raise) if Kafka is unavailable."""
        if not self._ready or self._producer is None:
            return False
        try:
            await self._producer.send_and_wait(topic, value=_serialize(payload), key=key.encode("utf-8"))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to publish to %s: %s", topic, exc)
            return False
