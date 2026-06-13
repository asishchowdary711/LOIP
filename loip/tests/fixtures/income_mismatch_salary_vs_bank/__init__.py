"""Salary slip vs bank statement income mismatch fixture (DoD: salary_slip_vs_bank_mismatch_flags)."""

EXTRACTED_DATA = {
    "salary_slip": {"employer_name": "Acme Corp", "net_pay": "80000"},
    "bank_statement": {
        "salary_credits": [
            {"amount": 48000.0, "date": "01/01/2026", "narration": "NEFT SALARY CREDIT"},
        ],
    },
}
