"""Inflated salary slip vs bank credits fixture (DoD: income_inflation_reviews)."""

EXTRACTED_DATA = {
    "salary_slip": {"employer_name": "Acme Corp", "net_pay": "120000"},
    "bank_statement": {
        "salary_credits": [
            {"amount": 70000.0, "date": "01/01/2026", "narration": "NEFT SALARY CREDIT"},
        ],
    },
}
