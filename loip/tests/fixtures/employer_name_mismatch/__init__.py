"""Salary slip employer differs from application employer (DoD: employer_name_mismatch_flags)."""

EXTRACTED_DATA = {
    "salary_slip": {"employer_name": "Acme Corp", "net_pay": "50000"},
    "bank_statement": {
        "salary_credits": [
            {"amount": 50000.0, "date": "01/01/2026", "narration": "SALARY"},
        ],
    },
}

APPLICATION_EMPLOYER_NAME = "Globex Industries Pvt Ltd"
