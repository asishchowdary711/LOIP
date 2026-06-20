import pytest
from loip.services.eligibility import calculate_eligibility


def test_basic_salary():
    result = calculate_eligibility(25_000)
    assert result["salary"] == 25_000
    assert result["max_principal"] == 537_000
    assert "FOIR" in result["rationale"]


def test_mid_salary():
    result = calculate_eligibility(50_000)
    assert result["max_principal"] == 10_74_000


def test_high_salary_no_artificial_cap():
    result = calculate_eligibility(200_000)
    assert result["max_principal"] == 42_97_000


def test_salary_below_minimum_raises():
    with pytest.raises(ValueError, match="Salary out of range"):
        calculate_eligibility(9_999)


def test_salary_zero_raises():
    with pytest.raises(ValueError, match="Salary out of range"):
        calculate_eligibility(0)


def test_salary_negative_raises():
    with pytest.raises(ValueError, match="Salary out of range"):
        calculate_eligibility(-50_000)


def test_salary_above_maximum_raises():
    with pytest.raises(ValueError, match="Salary out of range"):
        calculate_eligibility(10_00_00_001)
