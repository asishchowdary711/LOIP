"""Initial schema — applications, documents, evidence, consent, audit, review overrides.

Revision ID: 001
Revises: None
Create Date: 2026-06-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("applicant_name", sa.String(255), nullable=False),
        sa.Column("loan_amount", sa.Float, nullable=False),
        sa.Column("tenure_months", sa.Integer, nullable=False),
        sa.Column("employment_type", sa.String(20), nullable=False),
        sa.Column("employment_tier", sa.Integer, nullable=False),
        sa.Column("employer_name", sa.String(255), nullable=True),
        sa.Column("declared_monthly_income", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("applied_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime, nullable=True),
        sa.Column("decision", sa.String(20), nullable=True),
        sa.Column("risk_score", sa.Float, nullable=True),
        sa.Column("reason_codes", sa.JSON, nullable=True),
    )
    op.create_index("ix_applications_status", "applications", ["status"])
    op.create_index("ix_applications_applied_at", "applications", ["applied_at"])

    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), nullable=False, index=True),
        sa.Column("document_type", sa.String(30), nullable=False),
        sa.Column("minio_bucket", sa.String(50), nullable=False),
        sa.Column("minio_object_key", sa.String(255), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("is_synthetic", sa.Boolean, server_default=sa.text("false")),
        sa.Column("uploaded_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("extracted_fields", sa.JSON, nullable=True),
    )

    op.create_table(
        "evidence_chains",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), nullable=False, index=True),
        sa.Column("claim", sa.Text, nullable=False),
        sa.Column("reconciled_value", sa.Text, nullable=False),
        sa.Column("reconciliation_method", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("supporting_json", sa.JSON, nullable=False),
        sa.Column("contradicting_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "consent_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), nullable=False, index=True),
        sa.Column("data_principal_id", sa.String(36), nullable=False, index=True),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("consent_version", sa.String(10), nullable=False),
        sa.Column("consented_at", sa.DateTime, nullable=False),
        sa.Column("withdrawn_at", sa.DateTime, nullable=True),
        sa.Column("status", sa.String(15), server_default="active"),
        sa.Column("document_hash", sa.String(64), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
    )
    op.create_index("ix_consent_purpose_status", "consent_records", ["purpose", "status"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), nullable=False, index=True),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("detail", sa.JSON, nullable=True),
        sa.Column("timestamp", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "review_overrides",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), nullable=False, index=True),
        sa.Column("reviewer_id", sa.String(100), nullable=False),
        sa.Column("original_decision", sa.String(20), nullable=False),
        sa.Column("override_decision", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(50), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("overridden_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("review_overrides")
    op.drop_table("audit_log")
    op.drop_table("consent_records")
    op.drop_table("evidence_chains")
    op.drop_table("documents")
    op.drop_table("applications")
