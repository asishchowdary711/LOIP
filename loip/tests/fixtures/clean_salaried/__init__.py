"""Clean salaried applicant fixture — all checks pass (DoD: clean_salaried_application_approves)."""

APPLICATION_KWARGS = dict(
    application_id="FIX-CLEAN-SALARIED",
    applicant_name="Rajesh Kumar",
    loan_amount=500000,
    tenure_months=36,
    employment_type="salaried",
    employment_tier=2,
    employer_name="Acme Corp",
)

EXTRACTED_FIELDS = {
    "pan_number": "ABCDE1234F",
    "full_name": "Rajesh Kumar",
    "date_of_birth": "01/01/1990",
    "aadhaar_number": "234123412346",
}

EXTRACTED_DATA = {
    "salary_slip": {"employer_name": "Acme Corp", "net_pay": "50000"},
    "bank_statement": {
        "salary_credits": [
            {"amount": 50000.0, "date": "01/01/2026", "narration": "SALARY CREDIT ACME CORP"},
            {"amount": 50000.0, "date": "01/02/2026", "narration": "SALARY CREDIT ACME CORP"},
        ],
    },
}

APPLICATION_DATA = {
    "aadhaar_otp": "123456",
    "full_name": "Rajesh Kumar",
    "date_of_birth": "01/01/1990",
}
