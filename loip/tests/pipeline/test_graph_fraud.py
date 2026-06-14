"""Neo4j identity-graph fraud-ring detection (build-plan §7.3).

Gated on a reachable Neo4j (the docker-compose stack); skipped otherwise.
"""

from __future__ import annotations

import uuid

import pytest

from loip.domains.fraud.processor import FraudIntelligenceProcessor


def _graph_or_skip():
    try:
        from loip.graph import IdentityGraph

        return IdentityGraph()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Neo4j not reachable: {exc}")


def test_pan_farming_and_device_ring_detected():
    graph = _graph_or_skip()
    run = uuid.uuid4().hex[:8]
    shared_phone = f"99900{run[:5]}"
    shared_device = f"dev-{run}"

    # Three applications sharing one phone + device but with distinct PANs.
    apps = [
        (f"A-{run}", "AAAAA1111A", "234123412346"),
        (f"B-{run}", "BBBBB2222B", "234123412353"),
        (f"C-{run}", "CCCCC3333C", "234123412361"),
    ]
    try:
        for app_id, pan, aadhaar in apps:
            graph.ingest_application(app_id, {
                "pan": pan, "aadhaar": aadhaar,
                "phone": shared_phone, "device": shared_device,
            })

        signals = graph.detect_fraud_rings(apps[0][0])
        types = {s["signal_type"] for s in signals}
        assert "pan_farming" in types, "shared phone across distinct PANs should flag pan_farming"
        assert "synthetic_identity_ring" in types, "shared device should flag a ring"
    finally:
        # cleanup this run's nodes
        with graph.driver.session() as s:
            s.run(
                "MATCH (n) WHERE n.value IN $vals OR n.application_id IN $apps DETACH DELETE n",
                vals=[shared_phone, shared_device] + [p for _, p, _ in apps] + [a for _, _, a in apps],
                apps=[a for a, _, _ in apps],
            )
        graph.close()


def test_fraud_processor_uses_graph_signals():
    graph = _graph_or_skip()
    run = uuid.uuid4().hex[:8]
    shared_phone = f"98800{run[:5]}"
    proc = FraudIntelligenceProcessor(mock_mode=True)

    app1, app2 = f"P-{run}", f"Q-{run}"
    try:
        # Seed a colluding peer, then score the second through the processor.
        graph.ingest_application(app1, {"pan": "PPPPP1111P", "aadhaar": "234123412346", "phone": shared_phone})
        result = proc.process_fraud(
            app2,
            identity_result={},
            extracted_data={"pan": {"pan_number": "QQQQQ2222Q"}, "aadhaar": {"aadhaar_number": "234123412353"}},
            application_data={"phone": shared_phone},
            identity_graph=graph,
        )
        assert any(s.signal_type.value == "pan_farming" for s in result.signals)
        assert result.fraud_score > 0.5
    finally:
        with graph.driver.session() as s:
            s.run(
                "MATCH (n) WHERE n.value IN $vals OR n.application_id IN $apps DETACH DELETE n",
                vals=[shared_phone, "PPPPP1111P", "QQQQQ2222Q", "234123412346", "234123412353"],
                apps=[app1, app2],
            )
        graph.close()
