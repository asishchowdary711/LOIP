"""BIO label definitions per document type for LayoutLMv3 and Donut training."""

from __future__ import annotations

LABEL_SCHEMAS: dict[str, dict[str, str]] = {
    "pan": {
        "pan_number": "PAN_NUMBER",
        "full_name": "FULL_NAME",
        "father_name": "FATHER_NAME",
        "date_of_birth": "DATE_OF_BIRTH",
    },
    "aadhaar": {
        "aadhaar_number": "AADHAAR_NUMBER",
        "full_name": "FULL_NAME",
        "date_of_birth": "DATE_OF_BIRTH",
        "gender": "GENDER",
        "pincode": "PINCODE",
    },
    "salary_slip": {
        "employer_name": "EMPLOYER_NAME",
        "employee_name": "EMPLOYEE_NAME",
        "employee_pan": "EMPLOYEE_PAN",
        "uan": "UAN",
        "gross_pay": "GROSS_PAY",
        "net_pay": "NET_PAY",
        "basic": "BASIC",
        "hra": "HRA",
        "pf_deduction": "PF_DEDUCTION",
        "tds_deduction": "TDS_DEDUCTION",
        "pay_month": "PAY_MONTH",
        "pay_year": "PAY_YEAR",
    },
    "bank_statement": {
        "bank_name": "BANK_NAME",
        "account_number": "ACCOUNT_NUMBER",
        "account_holder_name": "ACCOUNT_HOLDER_NAME",
        "period_start": "PERIOD_START",
        "period_end": "PERIOD_END",
        "opening_balance": "OPENING_BALANCE",
        "closing_balance": "CLOSING_BALANCE",
    },
    "form16": {
        "employer_tan": "EMPLOYER_TAN",
        "employee_pan": "EMPLOYEE_PAN",
        "assessment_year": "ASSESSMENT_YEAR",
        "gross_salary": "GROSS_SALARY",
        "taxable_income": "TAXABLE_INCOME",
        "tds_deducted": "TDS_DEDUCTED",
    },
    "itr": {
        "pan_number": "PAN_NUMBER",
        "full_name": "FULL_NAME",
        "assessment_year": "ASSESSMENT_YEAR",
        "gross_total_income": "GROSS_TOTAL_INCOME",
        "total_tax_paid": "TOTAL_TAX_PAID",
    },
    "gst_return": {
        "gstin": "GSTIN",
        "legal_name": "LEGAL_NAME",
        "return_period": "RETURN_PERIOD",
        "total_taxable_value": "TOTAL_TAXABLE_VALUE",
        "total_tax_payable": "TOTAL_TAX_PAYABLE",
    },
}

BANK_STATEMENT_TXN_LABELS: dict[str, str] = {
    "date": "TXN_DATE",
    "narration": "TXN_NARRATION",
    "credit": "TXN_CREDIT",
    "debit": "TXN_DEBIT",
}

ADDRESS_LABELS: dict[str, str] = {
    "door": "ADDRESS_LINE",
    "street": "ADDRESS_LINE",
    "locality": "ADDRESS_LINE",
    "city": "ADDRESS_LINE",
    "state": "ADDRESS_LINE",
}


def get_bio_labels(doc_type: str) -> list[str]:
    schema = LABEL_SCHEMAS.get(doc_type, {})
    labels = ["O"]
    for tag in schema.values():
        labels.append(f"B-{tag}")
        labels.append(f"I-{tag}")
    if doc_type == "bank_statement":
        for tag in BANK_STATEMENT_TXN_LABELS.values():
            labels.append(f"B-{tag}")
            labels.append(f"I-{tag}")
    if doc_type == "aadhaar":
        labels.append("B-ADDRESS_LINE")
        labels.append("I-ADDRESS_LINE")
    return sorted(set(labels))


def label_to_id(doc_type: str) -> dict[str, int]:
    return {label: i for i, label in enumerate(get_bio_labels(doc_type))}


def id_to_label(doc_type: str) -> dict[int, str]:
    return {i: label for i, label in enumerate(get_bio_labels(doc_type))}
