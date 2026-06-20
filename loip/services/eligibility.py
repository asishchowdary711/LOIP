def calculate_eligibility(salary: int) -> dict:
    if salary < 10_000 or salary > 10_00_00_000:
        raise ValueError("Salary out of range")

    max_principal = min(salary * 24, 40_00_000)

    return {
        "salary": salary,
        "max_principal": max_principal,
        "multiplier": 24,
        "rate_pa": 0.12,
        "tenure_months": [12, 24, 36, 48, 60],
    }
