"""Seed the dev database with realistic sample onboarding data.

Generates a handful of synthetic test cases (via
``scripts/generators/generate_case.py``), runs each through the onboarding
pipeline in mock mode, and persists the resulting applications, documents,
evidence chains, consent records, and audit log entries.

Run from the repo root (``/workspaces/LOIP``), so that both the ``loip.*``
package and the top-level ``schemas``/``scripts`` packages resolve:

    python -m scripts.seed_db --reset
    python -m scripts.seed_db --database-url sqlite+aiosqlite:///./dev.db
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from loip.evaluate import build_mock_images
from loip.pipelines.onboarding import OnboardingPipeline
from loip.schemas.consent import ConsentPurpose, ConsentStatus
from loip.schemas.db_models import (
    ApplicationRecord,
    AuditLogRecord,
    Base,
    ConsentRecordDB,
    DocumentRecord,
    EvidenceRecord,
)
from loip.schemas.decision import Decision, LoanApplication, OnboardingDecision
from scripts.generators.generate_case import generate_case

# Mock PAN/Aadhaar extraction always returns this identity (see loip/evaluate.py) —
# scenarios use it for application_data["full_name"] unless deliberately mismatching.
MOCK_IDENTITY = {"full_name": "Mock User", "date_of_birth": "01/01/1990"}

# manifest "documents" key -> (file prefix used by save_metadata, MinIO bucket)
DOCUMENT_TYPE_INFO: dict[str, tuple[str, str]] = {
    "pan_card": ("pan", "pan-cards"),
    "aadhaar": ("aadhaar", "aadhaar-cards"),
    "salary_slip": ("salary_slip", "salary-slips"),
    "bank_statement": ("bank_statement", "bank-statements"),
    "form16": ("form16", "form16"),
    "itr": ("itr", "itr"),
    "offer_letter": ("offer_letter", "offer-letters"),
}

# Each scenario drives a different combination of pipeline outcomes (see
# loip/domains/risk_decisioning/processor.py for the underlying rules):
#   - employer_name=None / full_name=None means "use the value generated for
#     this case" instead of the value the mock extractor would return,
#     deliberately creating a mismatch.
SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "clean_salaried_approve",
        "segment": "salaried",
        "employer_tier": 2,
        "employer_name": "Acme Corp",
        "full_name": "Mock User",
        "loan_amount": 500_000,
        "tenure_months": 36,
    },
    {
        "name": "self_employed_clean_approve",
        "segment": "self_employed",
        "employer_tier": 2,
        "employer_name": "Acme Corp",
        "full_name": "Mock User",
        "loan_amount": 500_000,
        "tenure_months": 36,
        "include_itr": True,
    },
    {
        "name": "employer_mismatch_review",
        "segment": "salaried",
        "employer_tier": 2,
        "employer_name": None,
        "full_name": "Mock User",
        "loan_amount": 500_000,
        "tenure_months": 36,
    },
    {
        "name": "foir_marginal_review",
        "segment": "salaried",
        "employer_tier": 2,
        "employer_name": "Acme Corp",
        "full_name": "Mock User",
        "loan_amount": 800_000,
        "tenure_months": 36,
    },
    {
        "name": "employment_tier_high_risk_review",
        "segment": "salaried",
        "employer_tier": 5,
        "employer_name": "Acme Corp",
        "full_name": "Mock User",
        "loan_amount": 500_000,
        "tenure_months": 36,
    },
    {
        "name": "foir_exceeded_reject",
        "segment": "salaried",
        "employer_tier": 2,
        "employer_name": "Acme Corp",
        "full_name": "Mock User",
        "loan_amount": 2_000_000,
        "tenure_months": 12,
    },
    {
        "name": "identity_mismatch_reject",
        "segment": "salaried",
        "employer_tier": 2,
        "employer_name": "Acme Corp",
        "full_name": None,
        "loan_amount": 500_000,
        "tenure_months": 36,
    },
]

_STATUS_BY_DECISION = {
    Decision.APPROVE: "approved",
    Decision.REVIEW: "in_review",
    Decision.REJECT: "rejected",
}


def build_scenario_case(
    output_dir: Path, scenario: dict[str, Any]
) -> tuple[dict[str, Any], Path, LoanApplication, dict[str, Any]]:
    manifest = generate_case(
        output_dir,
        segment=scenario["segment"],
        include_itr=scenario.get("include_itr", False),
    )
    case_dir = output_dir / f"case_{manifest['case_id']}"

    application = LoanApplication(
        application_id=manifest["case_id"],
        applicant_name=manifest["applicant_name"],
        loan_amount=scenario["loan_amount"],
        tenure_months=scenario["tenure_months"],
        employment_type=manifest["segment"],
        employment_tier=scenario["employer_tier"],
        employer_name=scenario["employer_name"] or manifest["employer_name"],
    )
    application_data = application.model_dump(mode="json")
    application_data["full_name"] = scenario["full_name"] or manifest["applicant_name"]
    application_data["date_of_birth"] = MOCK_IDENTITY["date_of_birth"]
    application_data["aadhaar_otp"] = "123456"
    return manifest, case_dir, application, application_data


def build_document_records(
    application_id: str, manifest: dict[str, Any], case_dir: Path
) -> list[DocumentRecord]:
    records = []
    for doc_key, doc_id in manifest["documents"].items():
        prefix, bucket = DOCUMENT_TYPE_INFO[doc_key]

        extracted_fields = None
        meta_path = case_dir / f"{prefix}_{doc_id}.json"
        if meta_path.exists():
            with open(meta_path) as f:
                extracted_fields = json.load(f)

        for content_path in sorted(case_dir.glob(f"{prefix}_{doc_id}*")):
            if content_path.suffix == ".json":
                continue
            records.append(DocumentRecord(
                application_id=application_id,
                document_type=prefix,
                minio_bucket=bucket,
                minio_object_key=f"{case_dir.name}/{content_path.name}",
                file_hash=hashlib.sha256(content_path.read_bytes()).hexdigest(),
                is_synthetic=True,
                extracted_fields=extracted_fields,
            ))
    return records


def build_evidence_records(application_id: str, decision: OnboardingDecision) -> list[EvidenceRecord]:
    records = []
    for chain in decision.evidence_chains:
        records.append(EvidenceRecord(
            application_id=application_id,
            claim=chain.claim,
            reconciled_value=str(chain.reconciled_value),
            reconciliation_method=chain.reconciliation_method.value,
            confidence=chain.confidence,
            supporting_json=[f.model_dump(mode="json") for f in chain.supporting],
            contradicting_json=[f.model_dump(mode="json") for f in chain.contradicting] or None,
        ))
    return records


def build_consent_record(application_id: str) -> ConsentRecordDB:
    return ConsentRecordDB(
        application_id=application_id,
        data_principal_id=f"DP-{application_id}",
        purpose=ConsentPurpose.CREDIT_BUREAU_PULL.value,
        consent_version="1.0",
        consented_at=datetime.now(UTC),
        status=ConsentStatus.ACTIVE.value,
        document_hash=hashlib.sha256(f"consent-{application_id}".encode()).hexdigest(),
        ip_address="127.0.0.1",
        user_agent="loip-seed-db/1.0",
    )


def build_audit_record(application_id: str, scenario_name: str, decision: OnboardingDecision) -> AuditLogRecord:
    return AuditLogRecord(
        application_id=application_id,
        actor="seed_db",
        action="onboarding_decision",
        detail={
            "scenario": scenario_name,
            "decision": decision.decision.value,
            "risk_score": decision.risk_score,
            "reason_codes": [rc.code for rc in decision.reason_codes],
            "review_flags": decision.review_flags,
        },
    )


async def seed_database(database_url: str, output_dir: Path, *, reset: bool = False) -> list[dict[str, Any]]:
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        if reset:
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    pipeline = OnboardingPipeline(mock_mode=True)
    summaries = []

    async with session_factory() as session:
        for scenario in SCENARIOS:
            manifest, case_dir, application, application_data = build_scenario_case(output_dir, scenario)
            images = build_mock_images()
            decision = await pipeline.execute(application, images, application_data)

            session.add(ApplicationRecord(
                id=application.application_id,
                applicant_name=application.applicant_name,
                loan_amount=application.loan_amount,
                tenure_months=application.tenure_months,
                employment_type=application.employment_type,
                employment_tier=application.employment_tier,
                employer_name=application.employer_name,
                declared_monthly_income=application.declared_monthly_income,
                status=_STATUS_BY_DECISION[decision.decision],
                decided_at=decision.decided_at,
                decision=decision.decision.value,
                risk_score=decision.risk_score,
                reason_codes=[rc.model_dump(mode="json") for rc in decision.reason_codes] or None,
            ))
            for record in build_document_records(application.application_id, manifest, case_dir):
                session.add(record)
            for record in build_evidence_records(application.application_id, decision):
                session.add(record)
            session.add(build_consent_record(application.application_id))
            session.add(build_audit_record(application.application_id, scenario["name"], decision))

            summaries.append({
                "scenario": scenario["name"],
                "application_id": application.application_id,
                "applicant_name": application.applicant_name,
                "decision": decision.decision.value,
                "risk_score": decision.risk_score,
                "evidence_chains": len(decision.evidence_chains),
            })

        await session.commit()

    await engine.dispose()
    return summaries


@click.command()
@click.option(
    "--database-url", default=None,
    help="SQLAlchemy async DB URL (default: $DATABASE_URL or sqlite+aiosqlite:///./dev.db)",
)
@click.option(
    "--output-dir", type=click.Path(path_type=Path), default=None,
    help="Where to write generated case documents (default: loip/data/seed_cases)",
)
@click.option("--reset", is_flag=True, help="Drop and recreate all tables before seeding")
def main(database_url: str | None, output_dir: Path | None, reset: bool) -> None:
    db_url = database_url or os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./dev.db")
    out_dir = output_dir or Path(__file__).resolve().parents[1] / "data" / "seed_cases"
    out_dir.mkdir(parents=True, exist_ok=True)

    summaries = asyncio.run(seed_database(db_url, out_dir, reset=reset))

    click.echo(f"Seeded {len(summaries)} applications into {db_url}")
    click.echo(f"Generated case documents under {out_dir}\n")
    click.echo(f"{'scenario':<34} {'application_id':<10} {'decision':<10} {'risk_score':<10} evidence_chains")
    for s in summaries:
        risk_score = "-" if s["risk_score"] is None else f"{s['risk_score']:.2f}"
        click.echo(
            f"{s['scenario']:<34} {s['application_id']:<10} {s['decision']:<10} "
            f"{risk_score:<10} {s['evidence_chains']}"
        )


if __name__ == "__main__":
    main()
