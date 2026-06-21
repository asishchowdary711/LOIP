FOIR_CAP = 0.50
RATE_PA = 0.14
TENURE_M = 60


def calculate_eligibility(salary: int) -> dict:
    if salary < 10_000 or salary > 10_00_00_000:
        raise ValueError("Salary out of range")

    max_emi = salary * FOIR_CAP
    r = RATE_PA / 12
    factor = (r * (1 + r) ** TENURE_M) / ((1 + r) ** TENURE_M - 1)
    max_principal = int(max_emi / factor)
    max_principal = (max_principal // 1000) * 1000

    return {
        "salary": salary,
        "max_principal": max_principal,
        "rationale": "FOIR ≤ 50% at 14% p.a. over 60 months (aligns with LightGBM affordability check)",
    }
