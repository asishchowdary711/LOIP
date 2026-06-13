"""Generate synthetic offer letter PDFs with ground-truth metadata."""

from __future__ import annotations

import random
import uuid
from datetime import date, timedelta
from pathlib import Path

import click
from fpdf import FPDF

from .base import fake, random_employer, random_indian_address, save_metadata

DESIGNATIONS = [
    "Software Engineer", "Senior Software Engineer", "Data Analyst",
    "Product Manager", "Business Analyst", "Operations Manager",
    "Associate Consultant", "Team Lead", "Account Manager",
]


def generate_offer_letter(
    output_dir: Path,
    tamper_type: str | None = None,
    employee_name: str | None = None,
    employer_tier: int | None = None,
) -> dict:
    doc_id = uuid.uuid4().hex[:8]
    emp_name = employee_name or fake.name()
    employer_name, tier = random_employer(employer_tier)
    designation = random.choice(DESIGNATIONS)
    location = random_indian_address()
    joining_date = date.today() - timedelta(days=random.randint(60, 1500))

    ctc_ranges = {1: (400000, 1200000), 2: (600000, 2500000), 3: (500000, 1800000), 4: (300000, 1000000), 5: (250000, 700000)}
    low, high = ctc_ranges[tier]
    ctc = random.randint(low, high)

    fields = {
        "id": doc_id,
        "document_type": "offer_letter",
        "company_name": employer_name,
        "company_tier": tier,
        "employee_name": emp_name,
        "designation": designation,
        "ctc": ctc,
        "joining_date": joining_date.strftime("%d/%m/%Y"),
        "location": f"{location['city']}, {location['state']}",
        "tamper_type": tamper_type,
    }

    if tamper_type == "employer_mismatch":
        alt, _ = random_employer(tier)
        while alt == employer_name:
            alt, _ = random_employer(tier)
        fields["company_name"] = alt
    elif tamper_type == "employer_shell":
        fields["company_name"] = fake.company() + " Pvt Ltd"
        fields["_cin_invalid"] = True
    elif tamper_type == "document_forgery":
        fields["_pdf_created_by"] = "GIMP 2.10"

    output_dir.mkdir(parents=True, exist_ok=True)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, employer_name, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, f"{location['city']}, {location['state']}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "OFFER OF EMPLOYMENT", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, (
        f"Dear {emp_name},\n\n"
        f"We are pleased to offer you the position of {designation} at {employer_name}. "
        f"Your annual Cost to Company (CTC) will be INR {ctc:,}. "
        f"Your date of joining is {joining_date.strftime('%d %B %Y')}.\n\n"
        f"Location: {location['city']}, {location['state']}.\n\n"
        "Please sign and return this letter to confirm your acceptance.\n\n"
        "Regards,\nHR Department"
    ))

    pdf_path = output_dir / f"offer_letter_{doc_id}.pdf"
    pdf.output(str(pdf_path))
    save_metadata(output_dir, "offer_letter", fields)
    return fields


@click.command()
@click.option("--output", "-o", type=click.Path(), default="./output/offer_letters")
@click.option("--count", "-n", type=int, default=1)
@click.option("--tamper-type", type=click.Choice(["employer_mismatch", "employer_shell", "document_forgery"]), default=None)
def main(output: str, count: int, tamper_type: str | None) -> None:
    out = Path(output)
    for i in range(count):
        fields = generate_offer_letter(out, tamper_type=tamper_type)
        click.echo(f"[{i+1}/{count}] {fields['company_name']} — {fields['employee_name']} — CTC ₹{fields['ctc']:,}")


if __name__ == "__main__":
    main()
