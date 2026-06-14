"""V-CIP (Video-based CIP) API routes — RBI January 2020 circular.

Drives an agent-led video-KYC session over its lifecycle. A session is
initiated only after DPDP ``video_kyc`` consent is on record; the agent then
captures a geotag, marks the OVD as presented (with live face/liveness scores),
records the borrower's answers to the random questions, uploads the call
recording to India-region storage, and finally completes the session, which
adjudicates every RBI gate and returns a pass/fail with reason codes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field

from loip.domains.compliance.processor import ComplianceProcessor
from loip.domains.identity_trust.vcip import VCIPProcessor, VCIPSessionNotFoundError
from loip.schemas.consent import ConsentPurpose
from loip.web.auth import AuthenticatedUser, require_permission
from loip.web.routes.consent import compliance as compliance_processor

router = APIRouter(prefix="/vcip", tags=["V-CIP"])
vcip = VCIPProcessor(mock_mode=True)


def _compliance() -> ComplianceProcessor:
    # Share the consent store with the compliance routes so a consent recorded
    # via POST /compliance/consent is visible here.
    return compliance_processor


def _get_session_or_404(session_id: str):
    try:
        return vcip.get_session(session_id)
    except VCIPSessionNotFoundError:
        raise HTTPException(status_code=404, detail="V-CIP session not found") from None


# --- Gating ---

@router.get("/required")
async def vcip_required(
    loan_amount: float,
    user: AuthenticatedUser = Depends(require_permission("onboard:read")),
):
    return {"loan_amount": loan_amount, "vcip_required": VCIPProcessor.is_required(loan_amount)}


# --- Lifecycle ---

class InitiateRequest(BaseModel):
    application_id: str
    loan_amount: float = Field(gt=0)
    agent_id: str | None = None


@router.post("/initiate")
async def initiate(
    req: InitiateRequest,
    user: AuthenticatedUser = Depends(require_permission("onboard:write")),
):
    consent_ok = _compliance().verify_consent(req.application_id, ConsentPurpose.VIDEO_KYC)
    if not consent_ok:
        raise HTTPException(
            status_code=403,
            detail="DPDP video_kyc consent required before initiating V-CIP",
        )
    session = vcip.initiate_session(
        application_id=req.application_id,
        loan_amount=req.loan_amount,
        consent_verified=consent_ok,
        agent_id=req.agent_id or user.user_id,
    )
    return session.model_dump()


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    user: AuthenticatedUser = Depends(require_permission("onboard:read")),
):
    return _get_session_or_404(session_id).model_dump()


class GeotagRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float | None = None


@router.post("/{session_id}/geotag")
async def capture_geotag(
    session_id: str,
    req: GeotagRequest,
    user: AuthenticatedUser = Depends(require_permission("onboard:write")),
):
    _get_session_or_404(session_id)
    session = vcip.capture_geotag(session_id, req.latitude, req.longitude, req.accuracy_m)
    return session.model_dump()


class OVDRequest(BaseModel):
    ovd_type: str = Field(description="aadhaar | pan | passport | driving_licence")
    liveness_score: float | None = Field(default=None, ge=0.0, le=1.0)
    face_match_score: float | None = Field(default=None, ge=0.0, le=1.0)


@router.post("/{session_id}/ovd")
async def present_ovd(
    session_id: str,
    req: OVDRequest,
    user: AuthenticatedUser = Depends(require_permission("onboard:write")),
):
    _get_session_or_404(session_id)
    session = vcip.present_ovd(
        session_id,
        ovd_type=req.ovd_type,
        liveness_score=req.liveness_score,
        face_match_score=req.face_match_score,
    )
    return session.model_dump()


class AnswerRequest(BaseModel):
    index: int = Field(ge=0)
    answer: str
    correct: bool | None = None


@router.post("/{session_id}/answer")
async def answer_question(
    session_id: str,
    req: AnswerRequest,
    user: AuthenticatedUser = Depends(require_permission("onboard:write")),
):
    _get_session_or_404(session_id)
    try:
        session = vcip.answer_question(session_id, req.index, req.answer, req.correct)
    except IndexError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return session.model_dump()


@router.post("/{session_id}/recording")
async def upload_recording(
    session_id: str,
    file: UploadFile,
    user: AuthenticatedUser = Depends(require_permission("onboard:write")),
):
    _get_session_or_404(session_id)
    data = await file.read()
    ext = (file.filename or "recording.webm").rsplit(".", 1)[-1]
    session = vcip.store_recording(session_id, data, ext=ext)
    return {
        "session_id": session.session_id,
        "recording_object_id": session.recording_object_id,
        "recording_stored": session.recording_stored,
    }


@router.post("/{session_id}/complete")
async def complete(
    session_id: str,
    user: AuthenticatedUser = Depends(require_permission("onboard:write")),
):
    _get_session_or_404(session_id)
    result = vcip.complete_session(session_id)
    return result.model_dump()


@router.post("/{session_id}/cancel")
async def cancel(
    session_id: str,
    user: AuthenticatedUser = Depends(require_permission("onboard:write")),
):
    _get_session_or_404(session_id)
    return vcip.cancel_session(session_id).model_dump()
