"""SQLAlchemy ORM models for PostgreSQL — evidence repository, applications, consent."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ApplicationRecord(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    applicant_name: Mapped[str] = mapped_column(String(255))
    loan_amount: Mapped[float] = mapped_column(Float)
    tenure_months: Mapped[int] = mapped_column(Integer)
    employment_type: Mapped[str] = mapped_column(String(20))
    employment_tier: Mapped[int] = mapped_column(Integer)
    employer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    declared_monthly_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    applied_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason_codes: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_applications_status", "status"),
        Index("ix_applications_applied_at", "applied_at"),
    )


class DocumentRecord(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    application_id: Mapped[str] = mapped_column(String(36), index=True)
    document_type: Mapped[str] = mapped_column(String(30))
    minio_bucket: Mapped[str] = mapped_column(String(50))
    minio_object_key: Mapped[str] = mapped_column(String(255))
    file_hash: Mapped[str] = mapped_column(String(64))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    extracted_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class EvidenceRecord(Base):
    __tablename__ = "evidence_chains"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    application_id: Mapped[str] = mapped_column(String(36), index=True)
    claim: Mapped[str] = mapped_column(Text)
    reconciled_value: Mapped[str] = mapped_column(Text)
    reconciliation_method: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[float] = mapped_column(Float)
    supporting_json: Mapped[dict] = mapped_column(JSON)
    contradicting_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ConsentRecordDB(Base):
    __tablename__ = "consent_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    application_id: Mapped[str] = mapped_column(String(36), index=True)
    data_principal_id: Mapped[str] = mapped_column(String(36), index=True)
    purpose: Mapped[str] = mapped_column(String(30))
    consent_version: Mapped[str] = mapped_column(String(10))
    consented_at: Mapped[datetime] = mapped_column(DateTime)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(15), default="active")
    document_hash: Mapped[str] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_consent_purpose_status", "purpose", "status"),
    )


class AuditLogRecord(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    application_id: Mapped[str] = mapped_column(String(36), index=True)
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(50))
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ReviewOverrideRecord(Base):
    __tablename__ = "review_overrides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    application_id: Mapped[str] = mapped_column(String(36), index=True)
    reviewer_id: Mapped[str] = mapped_column(String(100))
    original_decision: Mapped[str] = mapped_column(String(20))
    override_decision: Mapped[str] = mapped_column(String(20))
    reason_code: Mapped[str] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
