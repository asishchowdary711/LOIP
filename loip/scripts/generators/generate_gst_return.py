"""Generate synthetic GST return (GSTR-3B) PDFs with ground-truth metadata."""

from __future__ import annotations

import random
import uuid
from datetime import date
from pathlib import Path

import click
from fpdf import FPDF

from .base import fake, save_metadata


def _generate_gstin() -> str:
    state_code = str(random.randint(1, 37)).zfill(2)
    pan_chars = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=5))
    pan_digits = "".join(random.choices("0123456789", k=4))
    pan_last = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    entity = "1"
    check = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    return f"{state_code}{pan_chars}{pan_digits}{pan_last}{entity}Z{check}"


def generate_gst_return(
    output_dir: Path,
    tamper_type: str | None = None,
    business_name: str | None = None,
) -> dict:
    doc_id = uuid.uuid4().hex[:8]
    biz_name = business_name or fake.company()
    gstin = _generate_gstin()

    today = date.today()
    tax_period = f"{today.month - 1 or 12}/{today.year if today.month > 1 else today.year - 1}"

    turnover_b2b = random.randint(100000, 5000000)
    turnover_b2c = random.randint(50000, 2000000)
    total_turnover = turnover_b2b + turnover_b2c

    igst = int(total_turnover * 0.09 * random.uniform(0.2, 0.5))
    cgst = int(total_turnover * 0.09 * random.uniform(0.3, 0.6))
    sgst = cgst
    total_tax = igst + cgst + sgst

    fields = {
        "id": doc_id,
        "document_type": "gst_return",
        "gstin": gstin,
        "business_name": biz_name,
        "tax_period": tax_period,
        "turnover_b2b": turnover_b2b,
        "turnover_b2c": turnover_b2c,
        "total_turnover": total_turnover,
        "igst": igst,
        "cgst": cgst,
        "sgst": sgst,
        "total_tax_liability": total_tax,
        "tamper_type": tamper_type,
    }

    if tamper_type == "document_forgery":
        fields["_pdf_created_by"] = "Adobe Photoshop CC 2024"

    output_dir.mkdir(parents=True, exist_ok=True)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "GSTR-3B — Monthly Return", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, f"Tax Period: {tax_period}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    for label, val in [
        ("GSTIN", gstin), ("Business Name", biz_name),
        ("Turnover B2B", f"INR {turnover_b2b:,}"),
        ("Turnover B2C", f"INR {turnover_b2c:,}"),
        ("Total Turnover", f"INR {total_turnover:,}"),
        ("IGST", f"INR {igst:,}"), ("CGST", f"INR {cgst:,}"), ("SGST", f"INR {sgst:,}"),
        ("Total Tax Liability", f"INR {total_tax:,}"),
    ]:
        pdf.cell(55, 6, label + ":", new_x="RIGHT")
        pdf.cell(0, 6, str(val), new_x="LMARGIN", new_y="NEXT")

    pdf_path = output_dir / f"gst_return_{doc_id}.pdf"
    pdf.output(str(pdf_path))
    save_metadata(output_dir, "gst_return", fields)
    return fields


@click.command()
@click.option("--output", "-o", type=click.Path(), default="./output/gst_returns")
@click.option("--count", "-n", type=int, default=1)
@click.option("--tamper-type", type=click.Choice(["document_forgery"]), default=None)
def main(output: str, count: int, tamper_type: str | None) -> None:
    out = Path(output)
    for i in range(count):
        fields = generate_gst_return(out, tamper_type=tamper_type)
        click.echo(f"[{i+1}/{count}] {fields['business_name']} — Turnover ₹{fields['total_turnover']:,}")


if __name__ == "__main__":
    main()
