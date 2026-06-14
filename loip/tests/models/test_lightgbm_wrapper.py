import pytest

pytest.importorskip("lightgbm")

from loip.models.lightgbm_wrapper import LightGBMWrapper


def test_mock_mode_returns_default():
    w = LightGBMWrapper(mock_mode=True)
    assert w.predict({}) == 0.85


def test_real_predictions_in_range_and_ordered():
    w = LightGBMWrapper(mock_mode=False)

    affordable = w.predict({"foir": 0.2, "disposable_income": 50000, "liquidity_score": 0.9})
    strained = w.predict({"foir": 0.9, "disposable_income": -5000, "liquidity_score": 0.1})

    assert 0.0 <= affordable <= 1.0
    assert 0.0 <= strained <= 1.0
    assert affordable > strained
