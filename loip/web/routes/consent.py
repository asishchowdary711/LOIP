"""DPDP consent, data deletion, KFS, cooling-off, and AML API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from loip.domains.compliance.processor import ComplianceProcessor
from loip.schemas.consent import ConsentPurpose
from loip.web.auth import AuthenticatedUser, require_permission

router = APIRouter(prefix="/compliance", tags=["Compliance"])
compliance = ComplianceProcessor(mock_mode=True)


# --- Consent ---

class ConsentRequest(BaseModel):
    application_id: str
    data_principal_id: str
    purpose: ConsentPurpose
    consent_version: str = "1.0"
    document_hash: str
    ip_address: str | None = None


@router.post("/consent")
async def record_consent(
    req: ConsentRequest,
    user: AuthenticatedUser = Depends(require_permission("onboard:write")),
):
    record = compliance.record_consent(
        application_id=req.application_id,
        data_principal_id=req.data_principal_id,
        purpose=req.purpose,
        consent_version=req.consent_version,
        document_hash=req.document_hash,
        ip_address=req.ip_address,
    )
    return record.model_dump()


@router.get("/consent/{application_id}")
async def get_consents(
    application_id: str,
    user: AuthenticatedUser = Depends(require_permission("compliance:read")),
):
    return [c.model_dump() for c in compliance.get_consent_records(application_id)]


@router.post("/consent/{application_id}/withdraw")
async def withdraw_consent(
    application_id: str,
    purpose: ConsentPurpose,
    user: AuthenticatedUser = Depends(require_permission("compliance:write")),
):
    success = compliance.withdraw_consent(application_id, purpose)
    if not success:
        raise HTTPException(status_code=404, detail="No active consent found for this purpose")
    return {"status": "withdrawn", "application_id": application_id, "purpose": purpose}


# --- Data Deletion (DPDP Right to Erasure) ---

class DeletionRequest(BaseModel):
    data_principal_id: str


@router.delete("/applications/{application_id}/personal-data")
async def delete_personal_data(
    application_id: str,
    req: DeletionRequest,
    user: AuthenticatedUser = Depends(require_permission("compliance:delete")),
):
    result = compliance.delete_personal_data(application_id, req.data_principal_id)
    return result.model_dump()


@router.get("/applications/{application_id}/data-summary")
async def get_data_summary(
    application_id: str,
    user: AuthenticatedUser = Depends(require_permission("compliance:read")),
):
    return compliance.get_data_summary(application_id)


# --- KFS (Key Fact Statement) ---

class KFSRequest(BaseModel):
    loan_amount: float = Field(gt=0)
    tenure_months: int = Field(ge=12, le=60)
    annual_rate: float = Field(gt=0)
    processing_fee_pct: float = Field(default=0.02, ge=0, le=0.05)


@router.post("/kfs/{application_id}")
async def generate_kfs(
    application_id: str,
    req: KFSRequest,
    user: AuthenticatedUser = Depends(require_permission("onboard:write")),
):
    kfs = compliance.generate_kfs(
        application_id=application_id,
        loan_amount=req.loan_amount,
        tenure_months=req.tenure_months,
        annual_rate=req.annual_rate,
        processing_fee_pct=req.processing_fee_pct,
    )
    return kfs.model_dump()


@router.post("/kfs/{application_id}/disclose")
async def disclose_kfs(
    application_id: str,
    user: AuthenticatedUser = Depends(require_permission("onboard:write")),
):
    kfs = compliance.disclose_kfs(application_id)
    if kfs is None:
        raise HTTPException(status_code=404, detail="KFS not found")
    return kfs.model_dump()


@router.post("/kfs/{application_id}/accept")
async def accept_kfs(
    application_id: str,
    user: AuthenticatedUser = Depends(require_permission("onboard:write")),
):
    kfs = compliance.accept_kfs(application_id)
    if kfs is None:
        raise HTTPException(status_code=404, detail="KFS not found")
    return kfs.model_dump()


# --- Cooling-Off Period ---

@router.post("/cooling-off/{application_id}")
async def start_cooling_off(
    application_id: str,
    user: AuthenticatedUser = Depends(require_permission("onboard:write")),
):
    record = compliance.start_cooling_off(application_id)
    return record.model_dump()


@router.post("/cooling-off/{application_id}/cancel")
async def cancel_loan(
    application_id: str,
    user: AuthenticatedUser = Depends(require_permission("onboard:write")),
):
    record = compliance.cancel_within_cooling_off(application_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No cooling-off record found")
    return record.model_dump()


# --- AML Check ---

class AMLRequest(BaseModel):
    loan_amount: float
    fraud_score: float = 0.0


@router.post("/aml/{application_id}")
async def run_aml_check(
    application_id: str,
    req: AMLRequest,
    user: AuthenticatedUser = Depends(require_permission("compliance:read")),
):
    result = compliance.check_aml(application_id, req.loan_amount, req.fraud_score)
    return result.model_dump()


# --- Data Residency ---

@router.get("/data-residency")
async def check_data_residency(
    user: AuthenticatedUser = Depends(require_permission("compliance:read")),
):
    endpoints = {
        "postgresql": "postgresql://localhost:5432/loip",
        "minio": "http://localhost:9000",
        "opensearch": "http://localhost:9200",
        "neo4j": "bolt://localhost:7687",
        "redis": "redis://localhost:6379",
    }
    results = ComplianceProcessor.check_data_residency(endpoints)
    all_india = all(r.is_india_region for r in results)
    return {
        "compliant": all_india,
        "checks": [r.model_dump() for r in results],
    }
