"""Generate synthetic ITR (Income Tax Return) PDFs with ground-truth metadata."""

from __future__ import annotations

import random
import uuid
from datetime import date
from pathlib import Path

import click
from .base import IndianFPDF, fake, generate_pan, save_metadata


def generate_itr(
    output_dir: Path,
    tamper_type: str | None = None,
    applicant_name: str | None = None,
    applicant_pan: str | None = None,
    segment: str = "salaried",
) -> dict:
    doc_id = uuid.uuid4().hex[:8]
    name = applicant_name or fake.name()
    pan = applicant_pan or generate_pan()

    fy = date.today().year - 1
    assessment_year = f"{fy + 1}-{str(fy + 2)[-2:]}"
    itr_type = "ITR-1 (Sahaj)" if segment == "salaried" else "ITR-4 (Sugam)"

    if segment == "salaried":
        income_from_salary = random.randint(300000, 2500000)
        income_from_house = random.choice([0, 0, -random.randint(50000, 200000)])
        income_from_other = random.randint(0, 50000)
        gross_total_income = income_from_salary + income_from_house + income_from_other
        business_income = 0
    else:
        business_income = random.randint(500000, 5000000)
        income_from_salary = 0
        income_from_house = 0
        income_from_other = random.randint(0, 100000)
        gross_total_income = business_income + income_from_other

    sec_80c = min(random.randint(50000, 200000), 150000)
    sec_80d = random.choice([0, 25000, 50000])
    total_deductions = sec_80c + sec_80d
    total_income = max(gross_total_income - total_deductions, 0)
    tax_payable = max(int(total_income * random.uniform(0.10, 0.25)), 0)
    tds = int(tax_payable * random.uniform(0.85, 1.05))
    refund = max(tds - tax_payable, 0)

    fields = {
        "id": doc_id,
        "document_type": "itr",
        "itr_type": itr_type,
        "applicant_name": name,
        "pan": pan,
        "assessment_year": assessment_year,
        "financial_year": f"{fy}-{str(fy + 1)[-2:]}",
        "income_from_salary": income_from_salary,
        "income_from_house": income_from_house,
        "income_from_other": income_from_other,
        "business_income": business_income,
        "gross_total_income": gross_total_income,
        "sec_80c": sec_80c,
        "sec_80d": sec_80d,
        "total_deductions": total_deductions,
        "total_income": total_income,
        "tax_payable": tax_payable,
        "tds_claimed": tds,
        "refund": refund,
        "segment": segment,
        "tamper_type": tamper_type,
    }

    if tamper_type == "income_inflation":
        fields["gross_total_income"] = int(gross_total_income * random.uniform(1.4, 2.0))
    elif tamper_type == "document_forgery":
        fields["_pdf_created_by"] = "Adobe Photoshop CC 2024"

    output_dir.mkdir(parents=True, exist_ok=True)

    pdf = IndianFPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, f"Income Tax Return - {itr_type}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, f"Assessment Year: {assessment_year}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    pdf.set_font("Helvetica", "", 9)
    rows = [
        ("Name", name), ("PAN", pan),
        ("Gross Total Income", f"INR {gross_total_income:,}"),
        ("Total Deductions", f"INR {total_deductions:,}"),
        ("Total Income", f"INR {total_income:,}"),
        ("Tax Payable", f"INR {tax_payable:,}"),
        ("TDS Claimed", f"INR {tds:,}"),
        ("Refund", f"INR {refund:,}"),
    ]
    for label, val in rows:
        pdf.cell(55, 6, label + ":", new_x="RIGHT")
        pdf.cell(0, 6, str(val), new_x="LMARGIN", new_y="NEXT")

    pdf_path = output_dir / f"itr_{doc_id}.pdf"
    pdf.output(str(pdf_path))
    save_metadata(output_dir, "itr", fields)
    return fields


@click.command()
@click.option("--output", "-o", type=click.Path(), default="./output/itr")
@click.option("--count", "-n", type=int, default=1)
@click.option("--segment", type=click.Choice(["salaried", "self_employed"]), default="salaried")
@click.option("--tamper-type", type=click.Choice(["income_inflation", "document_forgery"]), default=None)
def main(output: str, count: int, segment: str, tamper_type: str | None) -> None:
    out = Path(output)
    for i in range(count):
        fields = generate_itr(out, tamper_type=tamper_type, segment=segment)
        click.echo(f"[{i+1}/{count}] {fields['applicant_name']} — {fields['itr_type']} — ₹{fields['gross_total_income']:,}")


if __name__ == "__main__":
    main()
