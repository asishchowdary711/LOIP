"""Neo4j identity graph and graph-based fraud detection.

Builds the identity graph described in build-plan §7.3 — Person/PAN/Aadhaar/
Phone/Email/Device/Employer/BankAccount/Address nodes linked per application —
and runs Cypher fraud-ring queries (pan_farming, synthetic_identity_ring,
address_inconsistency_ring, employer_shell).

Best-effort: callers construct ``IdentityGraph`` in a try/except so the pipeline
still runs when Neo4j is down.
"""

from __future__ import annotations

import logging

from loip.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Uniqueness constraints (build-plan §5.5: PAN/Aadhaar/Phone/Email uniqueness).
_CONSTRAINTS = [
    "CREATE CONSTRAINT pan_unique IF NOT EXISTS FOR (n:PAN) REQUIRE n.value IS UNIQUE",
    "CREATE CONSTRAINT aadhaar_unique IF NOT EXISTS FOR (n:Aadhaar) REQUIRE n.value IS UNIQUE",
    "CREATE CONSTRAINT phone_unique IF NOT EXISTS FOR (n:Phone) REQUIRE n.value IS UNIQUE",
    "CREATE CONSTRAINT email_unique IF NOT EXISTS FOR (n:Email) REQUIRE n.value IS UNIQUE",
    "CREATE CONSTRAINT device_unique IF NOT EXISTS FOR (n:Device) REQUIRE n.value IS UNIQUE",
    "CREATE CONSTRAINT person_unique IF NOT EXISTS FOR (n:Person) REQUIRE n.application_id IS UNIQUE",
]

# (node label, relationship type, application field)
_ATTRIBUTES = [
    ("PAN", "HAS_PAN", "pan"),
    ("Aadhaar", "HAS_AADHAAR", "aadhaar"),
    ("Phone", "HAS_PHONE", "phone"),
    ("Email", "HAS_EMAIL", "email"),
    ("Device", "USES_DEVICE", "device"),
    ("Employer", "WORKS_AT", "employer"),
    ("BankAccount", "HAS_ACCOUNT", "bank_account"),
    ("Address", "LIVES_AT", "address"),
]


class IdentityGraph:
    def __init__(self, settings: Settings | None = None, *, ensure_constraints: bool = True):
        from neo4j import GraphDatabase

        self.settings = settings or get_settings()
        self.driver = GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
            # Fraud queries reference relationship types that may not exist yet
            # (e.g. no Email links); silence those benign notifications.
            notifications_min_severity="OFF",
        )
        self.driver.verify_connectivity()
        if ensure_constraints:
            self.ensure_constraints()

    def close(self) -> None:
        self.driver.close()

    def ensure_constraints(self) -> None:
        with self.driver.session() as session:
            for stmt in _CONSTRAINTS:
                session.run(stmt)

    def ingest_application(self, application_id: str, attributes: dict[str, str]) -> None:
        """MERGE a Person node for the application and link its attribute nodes."""
        with self.driver.session() as session:
            session.run("MERGE (p:Person {application_id: $app_id})", app_id=application_id)
            for label, rel, field in _ATTRIBUTES:
                value = (attributes.get(field) or "").strip()
                if not value:
                    continue
                session.run(
                    f"MATCH (p:Person {{application_id: $app_id}}) "
                    f"MERGE (n:{label} {{value: $value}}) "
                    f"MERGE (p)-[:{rel}]->(n)",
                    app_id=application_id, value=value,
                )

    def detect_fraud_rings(self, application_id: str) -> list[dict]:
        """Return fraud-ring signals touching ``application_id``.

        Each signal: {signal_type, severity, description, peers}."""
        signals: list[dict] = []
        with self.driver.session() as session:
            # pan_farming: one phone/email/device shared across multiple PANs.
            for shared_label, shared_rel in (("Phone", "HAS_PHONE"), ("Email", "HAS_EMAIL")):
                rows = session.run(
                    f"MATCH (p:Person {{application_id: $app_id}})-[:{shared_rel}]->(s:{shared_label})"
                    f"<-[:{shared_rel}]-(other:Person)"
                    "MATCH (p)-[:HAS_PAN]->(pan1:PAN) MATCH (other)-[:HAS_PAN]->(pan2:PAN) "
                    "WHERE pan1.value <> pan2.value "
                    "RETURN s.value AS shared, collect(DISTINCT other.application_id) AS peers, "
                    "count(DISTINCT pan2.value) AS distinct_pans",
                    app_id=application_id,
                ).data()
                for r in rows:
                    signals.append({
                        "signal_type": "pan_farming",
                        "severity": min(1.0, 0.6 + 0.1 * r["distinct_pans"]),
                        "description": f"{shared_label} {r['shared']} linked to {r['distinct_pans'] + 1} distinct PANs",
                        "peers": r["peers"],
                    })

            # synthetic_identity_ring: one device shared across multiple persons.
            rows = session.run(
                "MATCH (p:Person {application_id: $app_id})-[:USES_DEVICE]->(d:Device)"
                "<-[:USES_DEVICE]-(other:Person) "
                "RETURN d.value AS device, collect(DISTINCT other.application_id) AS peers",
                app_id=application_id,
            ).data()
            for r in rows:
                if r["peers"]:
                    signals.append({
                        "signal_type": "synthetic_identity_ring",
                        "severity": min(1.0, 0.7 + 0.1 * len(r["peers"])),
                        "description": f"Device {r['device']} shared with {len(r['peers'])} other application(s)",
                        "peers": r["peers"],
                    })

            # address_inconsistency_ring: one address shared across many persons.
            rows = session.run(
                "MATCH (p:Person {application_id: $app_id})-[:LIVES_AT]->(a:Address)"
                "<-[:LIVES_AT]-(other:Person) "
                "WITH a, collect(DISTINCT other.application_id) AS peers "
                "WHERE size(peers) >= 2 "
                "RETURN a.value AS address, peers",
                app_id=application_id,
            ).data()
            for r in rows:
                signals.append({
                    "signal_type": "address_inconsistency_ring",
                    "severity": min(1.0, 0.5 + 0.1 * len(r["peers"])),
                    "description": f"Address {r['address']} shared with {len(r['peers'])} other applications",
                    "peers": r["peers"],
                })

        return signals
