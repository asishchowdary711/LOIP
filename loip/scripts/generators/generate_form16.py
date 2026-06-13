"""Generate synthetic Form 16 PDFs with ground-truth metadata."""

from __future__ import annotations

import random
import uuid
from datetime import date
from pathlib import Path

import click
from fpdf import FPDF

from .base import fake, generate_pan, random_employer, save_metadata


def generate_form16(
    output_dir: Path,
    tamper_type: str | None = None,
    employee_name: str | None = None,
    employee_pan: str | None = None,
    employer_tier: int | None = None,
) -> dict:
    doc_id = uuid.uuid4().hex[:8]
    emp_name = employee_name or fake.name()
    emp_pan = employee_pan or generate_pan()
    employer_name, tier = random_employer(employer_tier)
    employer_tan = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=4)) + str(random.randint(10000, 99999)) + random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    fy = date.today().year - 1
    assessment_year = f"{fy + 1}-{str(fy + 2)[-2:]}"

    gross_salary = random.randint(300000, 2500000)
    hra_exempt = int(gross_salary * random.uniform(0.10, 0.20))
    standard_deduction = 50000
    total_allowances = hra_exempt
    income_from_salary = gross_salary - total_allowances - standard_deduction

    sec_80c = min(random.randint(50000, 200000), 150000)
    sec_80d = random.choice([0, 15000, 25000, 50000])
    sec_80e = random.choice([0, 0, 0, random.randint(10000, 50000)])
    sec_80g = random.choice([0, 0, random.randint(2000, 20000)])
    total_deductions = sec_80c + sec_80d + sec_80e + sec_80g

    taxable_income = max(income_from_salary - total_deductions, 0)
    if taxable_income <= 250000:
        tax = 0
    elif taxable_income <= 500000:
        tax = int((taxable_income - 250000) * 0.05)
    elif taxable_income <= 1000000:
        tax = 12500 + int((taxable_income - 500000) * 0.20)
    else:
        tax = 112500 + int((taxable_income - 1000000) * 0.30)
    cess = int(tax * 0.04)
    tds_deducted = tax + cess

    fields = {
        "id": doc_id,
        "document_type": "form16",
        "employer_name": employer_name,
        "employer_tan": employer_tan,
        "employee_name": emp_name,
        "employee_pan": emp_pan,
        "assessment_year": assessment_year,
        "financial_year": f"{fy}-{str(fy + 1)[-2:]}",
        "gross_salary": gross_salary,
        "hra_exemption": hra_exempt,
        "standard_deduction": standard_deduction,
        "total_allowances": total_allowances,
        "income_from_salary": income_from_salary,
        "sec_80c": sec_80c,
        "sec_80d": sec_80d,
        "sec_80e": sec_80e,
        "sec_80g": sec_80g,
        "total_deductions": total_deductions,
        "taxable_income": taxable_income,
        "tax_payable": tax,
        "cess": cess,
        "tds_deducted": tds_deducted,
        "tamper_type": tamper_type,
    }

    if tamper_type == "income_inflation":
        fields["gross_salary"] = int(gross_salary * random.uniform(1.3, 1.8))
    elif tamper_type == "document_forgery":
        fields["_pdf_created_by"] = "GIMP 2.10"

    output_dir.mkdir(parents=True, exist_ok=True)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "FORM No. 16", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, "Certificate under section 203 of the Income-tax Act, 1961", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Assessment Year: {assessment_year}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    pdf.set_font("Helvetica", "", 9)
    for label, val in [
        ("Employer Name", employer_name), ("Employer TAN", employer_tan),
        ("Employee Name", emp_name), ("Employee PAN", emp_pan),
        ("Gross Salary", f"INR {fields['gross_salary']:,}"),
        ("Deductions u/s 80C", f"INR {sec_80c:,}"),
        ("Deductions u/s 80D", f"INR {sec_80d:,}"),
        ("Taxable Income", f"INR {taxable_income:,}"),
        ("TDS Deducted", f"INR {tds_deducted:,}"),
    ]:
        pdf.cell(55, 6, label + ":", new_x="RIGHT")
        pdf.cell(0, 6, str(val), new_x="LMARGIN", new_y="NEXT")

    pdf_path = output_dir / f"form16_{doc_id}.pdf"
    pdf.output(str(pdf_path))
    save_metadata(output_dir, "form16", fields)
    return fields


@click.command()
@click.option("--output", "-o", type=click.Path(), default="./output/form16")
@click.option("--count", "-n", type=int, default=1)
@click.option("--tamper-type", type=click.Choice(["income_inflation", "document_forgery"]), default=None)
def main(output: str, count: int, tamper_type: str | None) -> None:
    out = Path(output)
    for i in range(count):
        fields = generate_form16(out, tamper_type=tamper_type)
        click.echo(f"[{i+1}/{count}] {fields['employee_name']} — AY {fields['assessment_year']} — Gross ₹{fields['gross_salary']:,}")


if __name__ == "__main__":
    main()
