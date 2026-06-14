import pytest

pytest.importorskip("sklearn")

from loip.models.graphsage_wrapper import GraphSAGEWrapper


def test_mock_mode_returns_default():
    w = GraphSAGEWrapper(mock_mode=True)
    score = w.predict_fraud(
        {"pan": "ABCDE1234F", "aadhaar": "123456789012"},
        {"application_id": "APP-001"},
    )
    assert score == 0.05


def test_missing_application_id_returns_default():
    w = GraphSAGEWrapper(mock_mode=False)
    score = w.predict_fraud({"pan": "ABCDE1234F", "aadhaar": "123456789012"}, {})
    assert score == 0.05


def test_real_mode_flags_shared_identifier_ring():
    w = GraphSAGEWrapper(mock_mode=False)

    isolated_score = w.predict_fraud(
        {"pan": "ABCDE1234F", "aadhaar": "123456789012"},
        {"application_id": "APP-001"},
    )
    other_isolated_score = w.predict_fraud(
        {"pan": "ZZZZZ9999Z", "aadhaar": "987654321098"},
        {"application_id": "APP-002"},
    )
    # APP-003 shares a pan with APP-001 -> ring signal
    ring_score = w.predict_fraud(
        {"pan": "ABCDE1234F", "aadhaar": "111122223333"},
        {"application_id": "APP-003"},
    )

    assert 0.0 <= isolated_score <= 1.0
    assert 0.0 <= other_isolated_score <= 1.0
    assert 0.0 <= ring_score <= 1.0
    assert ring_score > isolated_score
    assert ring_score > other_isolated_score
