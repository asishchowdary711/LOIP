"""Generate the §5.4 annotation-corpus training volume (10,500 documents).

Runs the 8 Indian KYC document generators to produce the clean/tampered
sample counts required before LayoutLMv3/Donut annotation:

| Document Type   | Clean | Tampered | Total |
|------------------|-------|----------|-------|
| PAN Card         | 1,000 |   500    | 1,500 |
| Aadhaar Card     | 1,000 |   500    | 1,500 |
| Salary Slip      | 2,000 | 1,000    | 3,000 |
| Bank Statement   | 2,000 | 1,000    | 3,000 |
| Form 16          |   500 |   250    |   750 |
| ITR              |   500 |   250    |   750 |
| Total            | 7,000 | 3,500    |10,500 |

Tampered counts are split evenly across each generator's supported
--tamper-type values.
"""

from __future__ import annotations

import logging
from pathlib import Path

import click

from scripts.generators.base import fake, generate_pan, random_dob, random_employer, random_salary_components
from scripts.generators.generate_aadhaar import generate_aadhaar
from scripts.generators.generate_bank_statement import generate_bank_statement
from scripts.generators.generate_form16 import generate_form16
from scripts.generators.generate_itr import generate_itr
from scripts.generators.generate_pan_card import generate_pan_card
from scripts.generators.generate_salary_slip import generate_salary_slip

logger = logging.getLogger(__name__)


PAN_TAMPER_TYPES = ["pan_mismatch", "identity_mismatch", "dob_mismatch", "document_forgery"]
AADHAAR_TAMPER_TYPES = ["identity_mismatch", "dob_mismatch", "synthetic_identity", "document_forgery"]
SALARY_SLIP_TAMPER_TYPES = ["income_inflation", "employer_mismatch", "pan_mismatch", "missing_fields", "document_forgery"]
BANK_STATEMENT_TAMPER_TYPES = ["income_deflation", "document_forgery"]
FORM16_TAMPER_TYPES = ["income_inflation", "document_forgery"]
ITR_TAMPER_TYPES = ["income_inflation", "document_forgery"]


def _tamper_sequence(total: int, types: list[str]) -> list[str | None]:
    """Distribute `total` tampered samples evenly across `types`."""
    n = len(types)
    base = total // n
    remainder = total % n
    seq: list[str | None] = []
    for i, t in enumerate(types):
        count = base + (1 if i < remainder else 0)
        seq.extend([t] * count)
    return seq


def generate_pan_corpus(out_dir: Path, clean: int, tampered: int) -> int:
    target = out_dir / "pan_card"
    target.mkdir(parents=True, exist_ok=True)
    for _ in range(clean):
        generate_pan_card(target, tamper_type=None)
    for tamper_type in _tamper_sequence(tampered, PAN_TAMPER_TYPES):
        generate_pan_card(target, tamper_type=tamper_type)
    return clean + tampered


def generate_aadhaar_corpus(out_dir: Path, clean: int, tampered: int) -> int:
    target = out_dir / "aadhaar"
    target.mkdir(parents=True, exist_ok=True)
    for _ in range(clean):
        generate_aadhaar(target, tamper_type=None)
    for tamper_type in _tamper_sequence(tampered, AADHAAR_TAMPER_TYPES):
        generate_aadhaar(target, tamper_type=tamper_type)
    return clean + tampered


def generate_salary_slip_corpus(out_dir: Path, clean: int, tampered: int) -> int:
    target = out_dir / "salary_slip"
    target.mkdir(parents=True, exist_ok=True)

    def _one(tamper_type: str | None) -> None:
        applicant_name = fake.name()
        pan = generate_pan()
        _, tier = random_employer()
        generate_salary_slip(
            target, tamper_type=tamper_type,
            employee_name=applicant_name, employee_pan=pan, employer_tier=tier,
        )

    for _ in range(clean):
        _one(None)
    for tamper_type in _tamper_sequence(tampered, SALARY_SLIP_TAMPER_TYPES):
        _one(tamper_type)
    return clean + tampered


def generate_bank_statement_corpus(out_dir: Path, clean: int, tampered: int) -> int:
    target = out_dir / "bank_statement"
    target.mkdir(parents=True, exist_ok=True)

    def _one(tamper_type: str | None) -> None:
        applicant_name = fake.name()
        employer_name, tier = random_employer()
        salary = random_salary_components(tier)
        generate_bank_statement(
            target, tamper_type=tamper_type,
            account_holder_name=applicant_name,
            salary_amount=salary["net_pay"],
            employer_name=employer_name,
        )

    for _ in range(clean):
        _one(None)
    for tamper_type in _tamper_sequence(tampered, BANK_STATEMENT_TAMPER_TYPES):
        _one(tamper_type)
    return clean + tampered


def generate_form16_corpus(out_dir: Path, clean: int, tampered: int) -> int:
    target = out_dir / "form16"
    target.mkdir(parents=True, exist_ok=True)

    def _one(tamper_type: str | None) -> None:
        applicant_name = fake.name()
        pan = generate_pan()
        _, tier = random_employer()
        generate_form16(
            target, tamper_type=tamper_type,
            employee_name=applicant_name, employee_pan=pan, employer_tier=tier,
        )

    for _ in range(clean):
        _one(None)
    for tamper_type in _tamper_sequence(tampered, FORM16_TAMPER_TYPES):
        _one(tamper_type)
    return clean + tampered


def generate_itr_corpus(out_dir: Path, clean: int, tampered: int) -> int:
    target = out_dir / "itr"
    target.mkdir(parents=True, exist_ok=True)

    def _one(tamper_type: str | None) -> None:
        applicant_name = fake.name()
        pan = generate_pan()
        generate_itr(
            target, tamper_type=tamper_type,
            applicant_name=applicant_name, applicant_pan=pan, segment="salaried",
        )

    for _ in range(clean):
        _one(None)
    for tamper_type in _tamper_sequence(tampered, ITR_TAMPER_TYPES):
        _one(tamper_type)
    return clean + tampered


VOLUME_TARGETS: dict[str, tuple[int, int]] = {
    "pan_card": (1000, 500),
    "aadhaar": (1000, 500),
    "salary_slip": (2000, 1000),
    "bank_statement": (2000, 1000),
    "form16": (500, 250),
    "itr": (500, 250),
}

GENERATORS = {
    "pan_card": generate_pan_corpus,
    "aadhaar": generate_aadhaar_corpus,
    "salary_slip": generate_salary_slip_corpus,
    "bank_statement": generate_bank_statement_corpus,
    "form16": generate_form16_corpus,
    "itr": generate_itr_corpus,
}


@click.command()
@click.option("--output", "-o", type=click.Path(), default="data/annotation_corpus",
              help="Root output directory for the annotation corpus")
@click.option("--doc-type", type=click.Choice(list(VOLUME_TARGETS.keys()) + ["all"]), default="all",
              help="Generate only this document type, or 'all'")
@click.option("--scale", type=float, default=1.0,
              help="Scale factor applied to clean/tampered targets (e.g. 0.1 for a smoke test)")
def main(output: str, doc_type: str, scale: float) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)

    doc_types = list(VOLUME_TARGETS.keys()) if doc_type == "all" else [doc_type]

    grand_total = 0
    for dt in doc_types:
        clean, tampered = VOLUME_TARGETS[dt]
        clean = max(1, int(clean * scale))
        tampered = max(1, int(tampered * scale))
        click.echo(f"Generating {dt}: {clean} clean + {tampered} tampered = {clean + tampered}")
        n = GENERATORS[dt](out, clean, tampered)
        grand_total += n
        click.echo(f"  done -> {out / dt} ({n} documents)")

    click.echo(f"\nTotal generated: {grand_total}")


if __name__ == "__main__":
    main()
