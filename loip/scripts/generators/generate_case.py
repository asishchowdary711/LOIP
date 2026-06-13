"""Compose multi-document test cases from individual generators."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import click

from .base import fake, generate_pan, random_dob, random_employer, random_salary_components
from .generate_aadhaar import generate_aadhaar
from .generate_bank_statement import generate_bank_statement
from .generate_form16 import generate_form16
from .generate_itr import generate_itr
from .generate_offer_letter import generate_offer_letter
from .generate_pan_card import generate_pan_card
from .generate_salary_slip import generate_salary_slip


TAMPER_PRESETS = {
    "clean": {},
    "income_mismatch": {"salary_slip": "income_inflation"},
    "identity_mismatch": {"pan": "identity_mismatch", "aadhaar": "identity_mismatch"},
    "dob_mismatch": {"pan": "dob_mismatch", "aadhaar": "dob_mismatch"},
    "income_inflated": {"salary_slip": "income_inflation", "form16": "income_inflation"},
    "employer_mismatch": {"salary_slip": "employer_mismatch"},
    "pan_mismatch": {"salary_slip": "pan_mismatch"},
    "document_forgery": {"pan": "document_forgery", "salary_slip": "document_forgery"},
    "synthetic_identity": {"aadhaar": "synthetic_identity"},
    "missing_fields": {"salary_slip": "missing_fields"},
}


def generate_case(
    output_dir: Path,
    tamper_type: str = "clean",
    segment: str = "salaried",
    include_form16: bool = False,
    include_itr: bool = False,
    include_offer_letter: bool = False,
) -> dict:
    case_id = uuid.uuid4().hex[:8]
    case_dir = output_dir / f"case_{case_id}"
    case_dir.mkdir(parents=True, exist_ok=True)

    applicant_name = fake.name()
    pan = generate_pan()
    dob = random_dob()
    employer_name, tier = random_employer()
    salary = random_salary_components(tier)

    tamper_map = TAMPER_PRESETS.get(tamper_type, {})

    pan_fields = generate_pan_card(
        case_dir, tamper_type=tamper_map.get("pan"),
        name=applicant_name, father_name=fake.name_male(),
    )

    aadhaar_fields = generate_aadhaar(
        case_dir, tamper_type=tamper_map.get("aadhaar"),
        name=applicant_name,
    )

    slip_fields = generate_salary_slip(
        case_dir, tamper_type=tamper_map.get("salary_slip"),
        employee_name=applicant_name, employee_pan=pan, employer_tier=tier,
    )

    bank_fields = generate_bank_statement(
        case_dir, tamper_type=tamper_map.get("bank_statement"),
        account_holder_name=applicant_name,
        salary_amount=salary["net_pay"],
        employer_name=employer_name,
    )

    case_manifest = {
        "case_id": case_id,
        "applicant_name": applicant_name,
        "pan": pan,
        "dob": dob.strftime("%d/%m/%Y"),
        "employer_name": employer_name,
        "employer_tier": tier,
        "segment": segment,
        "tamper_type": tamper_type,
        "documents": {
            "pan_card": pan_fields["id"],
            "aadhaar": aadhaar_fields["id"],
            "salary_slip": slip_fields["id"],
            "bank_statement": bank_fields["id"],
        },
    }

    if include_form16:
        f16 = generate_form16(
            case_dir, tamper_type=tamper_map.get("form16"),
            employee_name=applicant_name, employee_pan=pan, employer_tier=tier,
        )
        case_manifest["documents"]["form16"] = f16["id"]

    if include_itr:
        itr = generate_itr(
            case_dir, tamper_type=tamper_map.get("itr"),
            applicant_name=applicant_name, applicant_pan=pan, segment=segment,
        )
        case_manifest["documents"]["itr"] = itr["id"]

    if include_offer_letter:
        offer = generate_offer_letter(
            case_dir, tamper_type=tamper_map.get("offer_letter"),
            employee_name=applicant_name, employer_tier=tier,
        )
        case_manifest["documents"]["offer_letter"] = offer["id"]

    manifest_path = case_dir / "case_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(case_manifest, f, indent=2, default=str)

    return case_manifest


@click.command()
@click.option("--output", "-o", type=click.Path(), default="./test_cases")
@click.option("--count", "-n", type=int, default=1)
@click.option("--segment", type=click.Choice(["salaried", "self_employed"]), default="salaried")
@click.option("--tamper-type", type=click.Choice(list(TAMPER_PRESETS.keys())), default="clean")
@click.option("--include-form16", is_flag=True, help="Include Form 16")
@click.option("--include-itr", is_flag=True, help="Include ITR")
@click.option("--include-offer-letter", is_flag=True, help="Include offer letter")
def main(
    output: str, count: int, segment: str, tamper_type: str,
    include_form16: bool, include_itr: bool, include_offer_letter: bool,
) -> None:
    out = Path(output)
    for i in range(count):
        case = generate_case(
            out, tamper_type=tamper_type, segment=segment,
            include_form16=include_form16, include_itr=include_itr,
            include_offer_letter=include_offer_letter,
        )
        click.echo(f"[{i+1}/{count}] Case {case['case_id']} — {case['applicant_name']} — {tamper_type}")


if __name__ == "__main__":
    main()
