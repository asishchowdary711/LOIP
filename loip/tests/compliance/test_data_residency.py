"""CI gate: fails if any configured infrastructure endpoint resolves outside India region.

Mirrors the endpoint set used by GET /compliance/data-residency (web/routes/consent.py)
and ComplianceProcessor.check_data_residency (build plan §9.6).
"""

from fastapi.testclient import TestClient

from loip.domains.compliance.processor import ComplianceProcessor
from loip.web.api import app

# Dev-default endpoints — must all resolve to India region (localhost is treated
# as a local/dev stand-in for ap-south-1 infrastructure).
DEV_ENDPOINTS = {
    "postgresql": "postgresql://localhost:5432/loip",
    "minio": "http://localhost:9000",
    "opensearch": "http://localhost:9200",
    "neo4j": "bolt://localhost:7687",
    "redis": "redis://localhost:6379",
}


def test_dev_endpoints_are_india_region():
    results = ComplianceProcessor.check_data_residency(DEV_ENDPOINTS)
    assert all(r.is_india_region for r in results), [
        r.model_dump() for r in results if not r.is_india_region
    ]


def test_cross_region_endpoint_fails_check():
    results = ComplianceProcessor.check_data_residency(
        {"postgresql": "postgresql://db.us-east-1.rds.amazonaws.com:5432/loip"}
    )
    assert results[0].is_india_region is False
    assert results[0].region == "unknown"


def test_data_residency_endpoint_reports_compliant():
    client = TestClient(app)
    response = client.get(
        "/compliance/data-residency",
        headers={"X-API-Key": "compliance-key-001"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["compliant"] is True
    assert all(check["is_india_region"] for check in body["checks"])
