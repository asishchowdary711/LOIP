"""CLI to run the full onboarding pipeline against a generated test case.

Usage:
    python -m loip.evaluate --case-dir ./test_cases/case_a1b2c3d4/

``--case-dir`` must point to a directory produced by
``scripts/generators/generate_case.py`` (i.e. one containing
``case_manifest.json``).

Mock-mode caveat
-----------------
With ``mock_mode=True`` (the default — no GPU/OCR model weights are
available in this environment), document classification and field
extraction return canned values regardless of the input image (see the
mock branches of ``models/layoutlmv3_wrapper.py`` and
``models/qwen2_5_vl_wrapper.py``). In particular, PAN/Aadhaar extraction
always returns ``full_name="Mock User"`` / ``date_of_birth="01/01/1990"``,
so ``application_data`` is aligned to those values by default — otherwise
every case would hard-REJECT on ``identity_mismatch_name`` regardless of
its actual content.

The loan terms and employer name ARE taken from the case (or CLI
overrides) and do drive real decision variance: FOIR gates,
employer-name-mismatch review flags, employment-tier review flags, etc.

The images passed to the pipeline are placeholders (``np.zeros``) shaped
to match the mock classifier's height-based dispatch — real image loading
from ``--case-dir`` is future work, gated on the Phase 0/1a OCR model
training described in LOIP_BUILD_PLAN_v3_PersonalLoans_India.md.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import click
import numpy as np

from loip.pipelines.onboarding import OnboardingPipeline
from loip.schemas.decision import LoanApplication, OnboardingDecision

# Mock Qwen2.5-VL PAN/Aadhaar extraction always returns these values
# (models/qwen2_5_vl_wrapper.py) — align application_data to them so the
# identity cross-check doesn't hard-reject every case in mock mode.
MOCK_IDENTITY = {
    "full_name": "Mock User",
    "date_of_birth": "01/01/1990",
}

# Heights chosen to match the height-based mock classifier dispatch in
# models/layoutlmv3_wrapper.py: 100->PAN, 101->AADHAAR, 102->SALARY_SLIP,
# anything else -> SALARY_SLIP. The 4th image doubles as the selfie.
MOCK_IMAGE_SHAPES = [(100, 100), (101, 101), (102, 102), (103, 103)]


def load_case_manifest(case_dir: Path) -> dict[str, Any]:
    manifest_path = case_dir / "case_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"{manifest_path} not found — --case-dir must point to the output of "
            "scripts/generators/generate_case.py"
        )
    with open(manifest_path) as f:
        return json.load(f)


def build_application(
    manifest: dict[str, Any],
    *,
    loan_amount: float = 500_000.0,
    tenure_months: int = 36,
    declared_monthly_income: float | None = None,
) -> LoanApplication:
    return LoanApplication(
        application_id=manifest["case_id"],
        applicant_name=manifest["applicant_name"],
        loan_amount=loan_amount,
        tenure_months=tenure_months,
        employment_type=manifest.get("segment", "salaried"),
        employment_tier=manifest.get("employer_tier", 2),
        employer_name=manifest.get("employer_name"),
        declared_monthly_income=declared_monthly_income,
    )


def build_application_data(
    manifest: dict[str, Any],
    application: LoanApplication,
    *,
    mock_mode: bool = True,
) -> dict[str, Any]:
    data = application.model_dump(mode="json")
    if mock_mode:
        data.update(MOCK_IDENTITY)
    else:
        data["full_name"] = manifest["applicant_name"]
        data["date_of_birth"] = manifest.get("dob", "")
    data["aadhaar_otp"] = "123456"
    return data


def build_mock_images() -> list[np.ndarray]:
    return [np.zeros((h, w, 3), dtype=np.uint8) for h, w in MOCK_IMAGE_SHAPES]


async def run_case(
    case_dir: Path,
    *,
    mock_mode: bool = True,
    loan_amount: float = 500_000.0,
    tenure_months: int = 36,
    declared_monthly_income: float | None = None,
) -> tuple[dict[str, Any], OnboardingDecision]:
    manifest = load_case_manifest(case_dir)
    application = build_application(
        manifest,
        loan_amount=loan_amount,
        tenure_months=tenure_months,
        declared_monthly_income=declared_monthly_income,
    )
    application_data = build_application_data(manifest, application, mock_mode=mock_mode)
    images = build_mock_images()

    pipeline = OnboardingPipeline(mock_mode=mock_mode)
    decision = await pipeline.execute(application, images, application_data)
    return manifest, decision


def format_decision(manifest: dict[str, Any], decision: OnboardingDecision) -> dict[str, Any]:
    return {
        "case_id": manifest["case_id"],
        "tamper_type": manifest.get("tamper_type"),
        "decision": decision.decision.value,
        "risk_score": decision.risk_score,
        "reason_codes": [rc.model_dump(mode="json") for rc in decision.reason_codes],
        "review_flags": decision.review_flags,
        "identity_confidence": decision.identity_result.identity_confidence,
        "verified_monthly_income": decision.income_result.verified_monthly_income,
        "foir": decision.affordability_result.foir,
        "cibil_score": decision.bureau_result.score,
        "evidence_chain_count": len(decision.evidence_chains),
    }


def print_decision(manifest: dict[str, Any], decision: OnboardingDecision) -> None:
    summary = format_decision(manifest, decision)
    click.echo(f"Case:                    {summary['case_id']} (tamper_type={summary['tamper_type']})")
    click.echo(f"Decision:                {summary['decision'].upper()}")
    click.echo(f"Risk score:              {summary['risk_score']}")
    if summary["reason_codes"]:
        click.echo("Reason codes:")
        for rc in summary["reason_codes"]:
            detail = f" ({rc['detail']})" if rc.get("detail") else ""
            click.echo(f"  - {rc['code']} [{rc['category']}]{detail}")
    if summary["review_flags"]:
        click.echo("Review flags:")
        for flag in summary["review_flags"]:
            click.echo(f"  - {flag}")
    click.echo(f"Identity confidence:     {summary['identity_confidence']:.2f}")
    click.echo(f"Verified monthly income: Rs.{summary['verified_monthly_income']:,.0f}")
    click.echo(f"FOIR:                    {summary['foir']:.2f}")
    click.echo(f"CIBIL score:             {summary['cibil_score']}")
    click.echo(f"Evidence chains:         {summary['evidence_chain_count']}")


@click.command()
@click.option(
    "--case-dir", required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Directory produced by scripts/generators/generate_case.py (contains case_manifest.json)",
)
@click.option("--loan-amount", type=float, default=500_000.0, show_default=True, help="In INR")
@click.option("--tenure-months", type=int, default=36, show_default=True)
@click.option("--declared-income", type=float, default=None, help="Declared monthly income in INR")
@click.option(
    "--mock/--no-mock", default=True, show_default=True,
    help="Use mocked OCR/extraction/ML models (real model weights are not bundled with this repo)",
)
@click.option("--json", "as_json", is_flag=True, help="Print the decision as JSON")
def main(
    case_dir: Path,
    loan_amount: float,
    tenure_months: int,
    declared_income: float | None,
    mock: bool,
    as_json: bool,
) -> None:
    manifest, decision = asyncio.run(run_case(
        case_dir,
        mock_mode=mock,
        loan_amount=loan_amount,
        tenure_months=tenure_months,
        declared_monthly_income=declared_income,
    ))

    if as_json:
        click.echo(json.dumps({
            "summary": format_decision(manifest, decision),
            "decision": decision.model_dump(mode="json"),
        }, indent=2))
        return

    if mock:
        click.echo("(--mock: OCR/extraction is canned regardless of document content — see module docstring)\n")
    print_decision(manifest, decision)


if __name__ == "__main__":
    main()
