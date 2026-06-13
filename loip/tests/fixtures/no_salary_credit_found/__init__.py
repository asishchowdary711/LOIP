"""No recurring salary credits in bank statement (DoD: no_salary_credits_in_bank_rejects)."""

EXTRACTED_DATA = {
    "salary_slip": {"employer_name": "Acme Corp", "net_pay": "50000"},
    "bank_statement": {"salary_credits": []},
}
