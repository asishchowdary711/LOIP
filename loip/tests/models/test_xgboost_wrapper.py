import pytest

pytest.importorskip("xgboost")

from loip.models.xgboost_wrapper import XGBoostWrapper


def test_mock_mode_returns_per_task_defaults():
    w = XGBoostWrapper(mock_mode=True)
    assert w.predict({}, task="income_confidence") == 0.85
    assert w.predict({}, task="risk_score") == 0.82


def test_unknown_task_raises():
    w = XGBoostWrapper(mock_mode=True)
    with pytest.raises(ValueError):
        w.predict({}, task="not_a_task")


def test_income_confidence_real_predictions_in_range_and_ordered():
    w = XGBoostWrapper(mock_mode=False)

    clean = w.predict(
        {"salary_slip_amount": 50000, "bank_credit_amount": 50000, "anomalies": 0},
        task="income_confidence",
    )
    mismatched = w.predict(
        {"salary_slip_amount": 90000, "bank_credit_amount": 50000, "anomalies": 2},
        task="income_confidence",
    )

    assert 0.0 <= clean <= 1.0
    assert 0.0 <= mismatched <= 1.0
    assert clean > mismatched


def test_risk_score_real_predictions_in_range_and_ordered():
    w = XGBoostWrapper(mock_mode=False)

    strong = w.predict(
        {
            "identity_confidence": 0.95, "income_confidence": 0.9, "foir": 0.2,
            "cibil_score_normalized": 0.9, "cashflow_stability": 0.85,
            "employment_tier": 2, "loan_to_income_ratio": 1.0,
        },
        task="risk_score",
    )
    weak = w.predict(
        {
            "identity_confidence": 0.5, "income_confidence": 0.4, "foir": 0.9,
            "cibil_score_normalized": 0.3, "cashflow_stability": 0.2,
            "employment_tier": 5, "loan_to_income_ratio": 6.0,
        },
        task="risk_score",
    )

    assert 0.0 <= strong <= 1.0
    assert 0.0 <= weak <= 1.0
    assert strong > weak
    # consistent with the approval thresholds in domains/risk_decisioning/processor.py
    assert strong >= 0.70
    assert weak < 0.40
