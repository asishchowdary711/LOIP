"""Generate synthetic bank statement PDFs with ground-truth metadata."""

from __future__ import annotations

import random
import uuid
from datetime import date, timedelta
from pathlib import Path

import click

from .base import (
    BANK_NAMES,
    IndianFPDF,
    fake,
    random_indian_address,
    save_metadata,
)


def _generate_transactions(
    months: int,
    salary_amount: float,
    employer_name: str,
    opening_balance: float,
    tamper_type: str | None = None,
) -> tuple[list[dict], float]:
    transactions = []
    balance = opening_balance
    today = date.today()
    start_date = today.replace(day=1) - timedelta(days=months * 30)

    salary_narrations = [
        f"NEFT-SAL-{employer_name[:15].upper()}",
        f"SALARY {employer_name[:15].upper()}",
        f"SAL CR {employer_name[:10].upper()}",
    ]

    expense_narrations = [
        "UPI-SWIGGY", "UPI-ZOMATO", "UPI-AMAZON", "UPI-FLIPKART",
        "ATM WITHDRAWAL", "NEFT-RENT PAYMENT", "NACH-HDFC CARD",
        "POS-RELIANCE FRESH", "POS-DMART", "UPI-PHONEPE-ELECTRICITY",
        "NACH-TATA AIA INSURANCE", "UPI-IRCTC", "NACH-SIP MUTUAL FUND",
        "UPI-PETROL PUMP", "NEFT-SCHOOL FEES",
    ]

    emi_narrations = [
        "NACH-BAJAJ FINSERV EMI",
        "NACH-HDFC PERSONAL LOAN",
        "NACH-ICICI AUTO LOAN",
    ]

    existing_emis = random.randint(0, 2)
    emi_amounts = [random.randint(3000, 15000) for _ in range(existing_emis)]
    emi_days = [random.randint(1, 10) for _ in range(existing_emis)]

    current = start_date
    for month_idx in range(months):
        month_start = start_date + timedelta(days=month_idx * 30)

        salary_day = random.randint(25, 28) if month_idx > 0 else random.randint(1, 5)
        sal_date = month_start.replace(day=min(salary_day, 28))

        actual_salary = salary_amount
        if tamper_type == "income_deflation" and random.random() < 0.4:
            actual_salary = salary_amount * random.uniform(0.3, 0.7)

        balance += actual_salary
        transactions.append({
            "date": sal_date.strftime("%d/%m/%Y"),
            "narration": random.choice(salary_narrations),
            "credit": actual_salary,
            "debit": 0,
            "balance": round(balance, 2),
        })

        for emi_idx in range(existing_emis):
            emi_date = month_start.replace(day=min(emi_days[emi_idx], 28))
            balance -= emi_amounts[emi_idx]
            transactions.append({
                "date": emi_date.strftime("%d/%m/%Y"),
                "narration": emi_narrations[emi_idx % len(emi_narrations)],
                "credit": 0,
                "debit": emi_amounts[emi_idx],
                "balance": round(balance, 2),
            })

        num_expenses = random.randint(8, 20)
        for _ in range(num_expenses):
            exp_day = random.randint(1, 28)
            exp_date = month_start.replace(day=exp_day)
            amount = random.choice([
                random.randint(100, 500),
                random.randint(500, 2000),
                random.randint(2000, 8000),
                random.randint(8000, 25000),
            ])
            balance -= amount
            transactions.append({
                "date": exp_date.strftime("%d/%m/%Y"),
                "narration": random.choice(expense_narrations),
                "credit": 0,
                "debit": amount,
                "balance": round(balance, 2),
            })

        if random.random() < 0.3:
            misc_credit = random.randint(1000, 10000)
            balance += misc_credit
            transactions.append({
                "date": month_start.replace(day=random.randint(10, 25)).strftime("%d/%m/%Y"),
                "narration": random.choice(["UPI-REFUND", "NEFT-CASHBACK", "INT-INTEREST CREDIT"]),
                "credit": misc_credit,
                "debit": 0,
                "balance": round(balance, 2),
            })

    transactions.sort(key=lambda t: t["date"])
    return transactions, round(balance, 2)


class BankStatementPDF(IndianFPDF):
    def __init__(self, fields: dict):
        super().__init__()
        self.fields = fields
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 10, self.fields["bank_name"], align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5, "Statement of Account", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

        self.set_font("Helvetica", "", 8)
        self.cell(50, 5, f"Account Holder: {self.fields['account_holder_name']}", new_x="RIGHT")
        self.cell(0, 5, f"Account No: {self.fields['account_number']}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.cell(50, 5, f"Period: {self.fields['period_start']} to {self.fields['period_end']}", new_x="RIGHT")
        self.cell(0, 5, f"Branch: {self.fields.get('branch', 'Main Branch')}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(2)

    def _add_transactions(self):
        self.set_font("Helvetica", "B", 8)
        self.set_fill_color(220, 220, 220)
        col_widths = [22, 68, 25, 25, 30]
        headers = ["Date", "Narration", "Credit", "Debit", "Balance"]
        for w, h in zip(col_widths, headers):
            self.cell(w, 6, h, border=1, fill=True, align="C", new_x="RIGHT")
        self.ln()

        self.set_font("Helvetica", "", 7)
        for txn in self.fields["transactions"]:
            self.cell(col_widths[0], 5, txn["date"], border="LR", new_x="RIGHT")
            self.cell(col_widths[1], 5, txn["narration"][:40], border="LR", new_x="RIGHT")
            credit_str = f"{txn['credit']:,.0f}" if txn["credit"] else ""
            debit_str = f"{txn['debit']:,.0f}" if txn["debit"] else ""
            self.cell(col_widths[2], 5, credit_str, border="LR", align="R", new_x="RIGHT")
            self.cell(col_widths[3], 5, debit_str, border="LR", align="R", new_x="RIGHT")
            self.cell(col_widths[4], 5, f"{txn['balance']:,.0f}", border="LR", align="R", new_x="LMARGIN", new_y="NEXT")

        self.set_font("Helvetica", "B", 8)
        self.cell(sum(col_widths[:2]), 6, "Closing Balance", border=1, fill=True)
        self.cell(col_widths[2], 6, "", border=1)
        self.cell(col_widths[3], 6, "", border=1)
        self.cell(col_widths[4], 6, f"{self.fields['closing_balance']:,.0f}", border=1, align="R", new_x="LMARGIN", new_y="NEXT")

    def build(self) -> None:
        self.add_page()
        self._add_transactions()


def generate_bank_statement(
    output_dir: Path,
    tamper_type: str | None = None,
    account_holder_name: str | None = None,
    salary_amount: float | None = None,
    employer_name: str | None = None,
    months: int = 6,
) -> dict:
    doc_id = uuid.uuid4().hex[:8]
    holder_name = account_holder_name or fake.name()
    bank_name = random.choice(BANK_NAMES)
    account_number = "".join(random.choices("0123456789", k=random.choice([11, 12, 14])))
    salary = salary_amount or random.randint(25000, 120000)
    emp_name = employer_name or fake.company()
    opening_balance = random.randint(10000, 200000)

    today = date.today()
    period_end = today.replace(day=1) - timedelta(days=1)
    period_start = (period_end - timedelta(days=months * 30)).replace(day=1)

    transactions, closing_balance = _generate_transactions(
        months=months,
        salary_amount=salary,
        employer_name=emp_name,
        opening_balance=opening_balance,
        tamper_type=tamper_type,
    )

    address = random_indian_address()

    fields = {
        "id": doc_id,
        "document_type": "bank_statement",
        "bank_name": bank_name,
        "account_number": account_number,
        "account_holder_name": holder_name,
        "period_start": period_start.strftime("%d/%m/%Y"),
        "period_end": period_end.strftime("%d/%m/%Y"),
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
        "transactions": transactions,
        "salary_amount": salary,
        "employer_name": emp_name,
        "branch": f"{address['city']} {address['locality']}",
        "tamper_type": tamper_type,
    }

    if tamper_type == "document_forgery":
        fields["_pdf_created_by"] = "Adobe Photoshop CC 2024"

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf = BankStatementPDF(fields)
    pdf.build()
    pdf_path = output_dir / f"bank_statement_{doc_id}.pdf"
    pdf.output(str(pdf_path))

    save_metadata(output_dir, "bank_statement", fields)
    return fields


@click.command()
@click.option("--output", "-o", type=click.Path(), default="./output/bank_statements")
@click.option("--count", "-n", type=int, default=1)
@click.option("--months", "-m", type=int, default=6, help="Number of months in statement")
@click.option("--tamper-type", type=click.Choice(["income_deflation", "document_forgery"]), default=None)
def main(output: str, count: int, months: int, tamper_type: str | None) -> None:
    out = Path(output)
    for i in range(count):
        fields = generate_bank_statement(out, tamper_type=tamper_type, months=months)
        click.echo(f"[{i+1}/{count}] {fields['bank_name']} — {fields['account_holder_name']} — {len(fields['transactions'])} txns")


if __name__ == "__main__":
    main()
