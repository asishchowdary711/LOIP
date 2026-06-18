"""Fraud intelligence domain schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from .evidence import EvidenceChain


class FraudSignalType(StrEnum):
    DOCUMENT_FORGERY = "document_forgery"
    SYNTHETIC_IDENTITY_RING = "synthetic_identity_ring"
    PAN_FARMING = "pan_farming"
    EMPLOYEE_RECORD_FORGERY = "employee_record_forgery"
    ADDRESS_INCONSISTENCY_RING = "address_inconsistency_ring"
    EMPLOYER_SHELL = "employer_shell"
    BEHAVIORAL_ANOMALY = "behavioral_anomaly"
    INCOME_MANIPULATION = "income_manipulation"
    QR_SIGNATURE_INVALID = "qr_signature_invalid"
    QR_DATA_MISMATCH = "qr_data_mismatch"
    QR_TAMPERED = "qr_tampered"


class FraudSignal(BaseModel):
    signal_type: FraudSignalType
    severity: float = Field(ge=0.0, le=1.0)
    description: str
    evidence: EvidenceChain


class FraudResult(BaseModel):
    application_id: str
    fraud_score: float = Field(ge=0.0, le=1.0)
    signals: list[FraudSignal] = Field(default_factory=list)
    graph_fraud_score: float | None = Field(default=None, description="GraphSAGE score, Phase 2")
    behavioral_anomaly_score: float | None = Field(default=None, description="Isolation Forest, Phase 2")
    evidence_chains: list[EvidenceChain] = Field(default_factory=list)
