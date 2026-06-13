"""Generate synthetic salary slip PDFs with ground-truth metadata."""

from __future__ import annotations

import random
import uuid
from datetime import date
from pathlib import Path

import click
from fpdf import FPDF

from .base import (
    fake,
    generate_pan,
    generate_uan,
    random_employer,
    random_salary_components,
    save_metadata,
)


class SalarySlipPDF(FPDF):
    def __init__(self, fields: dict):
        super().__init__()
        self.fields = fields
        self.set_auto_page_break(auto=False)

    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, self.fields["employer_name"], align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5, "CIN: " + self.fields.get("employer_cin", "U72200MH2020PTC000000"), align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 8, f"Pay Slip for {self.fields['pay_month']} {self.fields['pay_year']}", align="C", new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)

    def _add_employee_details(self):
        self.set_font("Helvetica", "", 9)
        details = [
            ("Employee Name", self.fields["employee_name"]),
            ("Employee PAN", self.fields["employee_pan"]),
            ("UAN", self.fields["uan"]),
            ("Designation", self.fields.get("designation", "Software Engineer")),
            ("Department", self.fields.get("department", "Engineering")),
            ("Bank Account", self.fields.get("bank_account", "XXXX" + str(random.randint(1000, 9999)))),
        ]
        col_w = 95
        for i in range(0, len(details), 2):
            left = details[i]
            right = details[i + 1] if i + 1 < len(details) else ("", "")
            self.cell(30, 6, left[0] + ":", new_x="RIGHT")
            self.cell(col_w - 30, 6, str(left[1]), new_x="RIGHT")
            self.cell(30, 6, right[0] + ":", new_x="RIGHT")
            self.cell(col_w - 30, 6, str(right[1]), new_x="LMARGIN", new_y="NEXT")
        self.ln(5)

    def _add_earnings_deductions(self):
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(220, 220, 220)
        self.cell(95, 7, "Earnings", border=1, fill=True, align="C", new_x="RIGHT")
        self.cell(95, 7, "Deductions", border=1, fill=True, align="C", new_x="LMARGIN", new_y="NEXT")

        earnings = [
            ("Basic", self.fields["basic"]),
            ("HRA", self.fields["hra"]),
            ("Conveyance Allowance", self.fields["conveyance"]),
            ("Special Allowance", self.fields["special_allowance"]),
        ]
        deductions = [
            ("Provident Fund (PF)", self.fields["pf_deduction"]),
            ("Professional Tax (PT)", self.fields["professional_tax"]),
            ("Tax Deducted at Source", self.fields["tds_deduction"]),
        ]

        self.set_font("Helvetica", "", 9)
        max_rows = max(len(earnings), len(deductions))
        for i in range(max_rows):
            if i < len(earnings):
                self.cell(60, 6, earnings[i][0], border="L")
                self.cell(35, 6, f"{earnings[i][1]:,.0f}", border="R", align="R", new_x="RIGHT")
            else:
                self.cell(95, 6, "", border="LR", new_x="RIGHT")

            if i < len(deductions):
                self.cell(60, 6, deductions[i][0], border="L")
                self.cell(35, 6, f"{deductions[i][1]:,.0f}", border="R", align="R", new_x="LMARGIN", new_y="NEXT")
            else:
                self.cell(95, 6, "", border="LR", new_x="LMARGIN", new_y="NEXT")

        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(240, 240, 240)
        self.cell(60, 7, "Total Earnings", border=1, fill=True)
        self.cell(35, 7, f"{self.fields['gross_pay']:,.0f}", border=1, fill=True, align="R", new_x="RIGHT")
        total_deductions = self.fields["pf_deduction"] + self.fields["professional_tax"] + self.fields["tds_deduction"]
        self.cell(60, 7, "Total Deductions", border=1, fill=True)
        self.cell(35, 7, f"{total_deductions:,.0f}", border=1, fill=True, align="R", new_x="LMARGIN", new_y="NEXT")

        self.ln(5)
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 8, f"Net Pay: INR {self.fields['net_pay']:,.0f}", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 6, "This is a computer-generated document and does not require a signature.", align="C", new_x="LMARGIN", new_y="NEXT")

    def build(self) -> None:
        self.add_page()
        self._add_employee_details()
        self._add_earnings_deductions()


def generate_salary_slip(
    output_dir: Path,
    tamper_type: str | None = None,
    employee_name: str | None = None,
    employee_pan: str | None = None,
    employer_tier: int | None = None,
    pay_month: str | None = None,
    pay_year: int | None = None,
) -> dict:
    doc_id = uuid.uuid4().hex[:8]
    emp_name = employee_name or fake.name()
    emp_pan = employee_pan or generate_pan()
    employer_name, tier = random_employer(employer_tier)
    salary = random_salary_components(tier)

    months = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    month = pay_month or random.choice(months)
    year = pay_year or date.today().year

    fields = {
        "id": doc_id,
        "document_type": "salary_slip",
        "employer_name": employer_name,
        "employer_tier": tier,
        "employee_name": emp_name,
        "employee_pan": emp_pan,
        "uan": generate_uan(),
        "pay_month": month,
        "pay_year": year,
        "tamper_type": tamper_type,
        **salary,
    }

    if tamper_type == "income_inflation":
        factor = random.uniform(1.3, 1.8)
        for key in ["basic", "hra", "special_allowance", "gross_pay", "net_pay"]:
            fields[key] = int(fields[key] * factor)
    elif tamper_type == "employer_mismatch":
        alt_employer, _ = random_employer(tier)
        while alt_employer == employer_name:
            alt_employer, _ = random_employer(tier)
        fields["employer_name"] = alt_employer
    elif tamper_type == "pan_mismatch":
        fields["employee_pan"] = generate_pan()
    elif tamper_type == "missing_fields":
        for key in random.sample(["pf_deduction", "tds_deduction", "uan"], k=random.randint(1, 2)):
            fields[key] = ""
    elif tamper_type == "document_forgery":
        fields["_pdf_created_by"] = "Adobe Photoshop CC 2024"

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf = SalarySlipPDF(fields)
    pdf.build()
    pdf_path = output_dir / f"salary_slip_{doc_id}.pdf"
    pdf.output(str(pdf_path))

    save_metadata(output_dir, "salary_slip", fields)
    return fields


@click.command()
@click.option("--output", "-o", type=click.Path(), default="./output/salary_slips")
@click.option("--count", "-n", type=int, default=1)
@click.option("--tamper-type", type=click.Choice([
    "income_inflation", "employer_mismatch", "pan_mismatch", "missing_fields", "document_forgery"
]), default=None)
@click.option("--tier", type=click.IntRange(1, 5), default=None, help="Employer tier (1-5)")
def main(output: str, count: int, tamper_type: str | None, tier: int | None) -> None:
    out = Path(output)
    for i in range(count):
        fields = generate_salary_slip(out, tamper_type=tamper_type, employer_tier=tier)
        click.echo(f"[{i+1}/{count}] {fields['employer_name']} — {fields['employee_name']} — ₹{fields['net_pay']:,.0f}")


if __name__ == "__main__":
    main()
