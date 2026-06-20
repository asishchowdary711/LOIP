import pytest
from loip.services.eligibility import calculate_eligibility


def test_basic_salary():
    result = calculate_eligibility(25_000)
    assert result["salary"] == 25_000
    assert result["max_principal"] == 600_000
    assert result["multiplier"] == 24
    assert result["rate_pa"] == 0.12
    assert result["tenure_months"] == [12, 24, 36, 48, 60]


def test_high_salary_hits_cap():
    result = calculate_eligibility(200_000)
    assert result["max_principal"] == 40_00_000


def test_exact_cap_boundary():
    # salary * 24 == 40L exactly at salary = 166667
    result = calculate_eligibility(166_667)
    assert result["max_principal"] == min(166_667 * 24, 40_00_000)


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
