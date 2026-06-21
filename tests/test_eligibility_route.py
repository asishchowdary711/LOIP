from fastapi.testclient import TestClient
from loip.web.api import app

client = TestClient(app)


def test_eligibility_valid_salary():
    resp = client.get("/apply/eligibility", params={"salary": 35_000})
    assert resp.status_code == 200
    data = resp.json()
    assert data["salary"] == 35_000
    assert data["max_principal"] == 752_000
    assert "FOIR" in data["rationale"]


def test_eligibility_salary_too_low():
    resp = client.get("/apply/eligibility", params={"salary": 5_000})
    assert resp.status_code == 422


def test_eligibility_missing_salary():
    resp = client.get("/apply/eligibility")
    assert resp.status_code == 422


def test_eligibility_non_numeric():
    resp = client.get("/apply/eligibility", params={"salary": "abc"})
    assert resp.status_code == 422
