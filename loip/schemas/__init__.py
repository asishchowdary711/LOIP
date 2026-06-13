"""LOIP domain schemas — traceability contract and all domain outputs."""

from .affordability import AffordabilityFlag, AffordabilityResult
from .bureau import CreditBureauResult
from .consent import ConsentPurpose, ConsentRecord, ConsentStatus, DataDeletionRequest
from .decision import Decision, LoanApplication, OnboardingDecision, ReasonCode
from .evidence import (
    BoundingBox,
    DocumentType,
    EvidenceChain,
    ExtractionMethod,
    ExtractedField,
    ReconciliationMethod,
    SourceLocation,
)
from .fraud import FraudResult, FraudSignal, FraudSignalType
from .identity import (
    APIVerificationResult,
    EntityMatch,
    IdentityFlag,
    IdentityVerificationResult,
)
from .income import IncomeFlag, IncomeResult, IncomeSource, SalaryCredit

__all__ = [
    "AffordabilityFlag",
    "AffordabilityResult",
    "APIVerificationResult",
    "BoundingBox",
    "ConsentPurpose",
    "ConsentRecord",
    "ConsentStatus",
    "CreditBureauResult",
    "DataDeletionRequest",
    "Decision",
    "DocumentType",
    "EntityMatch",
    "EvidenceChain",
    "ExtractionMethod",
    "ExtractedField",
    "FraudResult",
    "FraudSignal",
    "FraudSignalType",
    "IdentityFlag",
    "IdentityVerificationResult",
    "IncomeFlag",
    "IncomeResult",
    "IncomeSource",
    "LoanApplication",
    "OnboardingDecision",
    "ReasonCode",
    "ReconciliationMethod",
    "SalaryCredit",
    "SourceLocation",
]
