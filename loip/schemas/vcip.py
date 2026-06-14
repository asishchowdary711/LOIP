"""Video-based Customer Identification Process (V-CIP) schemas.

Implements the RBI January 2020 V-CIP circular for fully digital personal-loan
onboarding without a branch visit. A V-CIP session is a live agent-led video
call in which the borrower presents an Officially Valid Document (OVD) to the
camera, answers random questions (liveness/authenticity), is geotagged inside
India, and the whole call is recorded to India-region storage (MinIO). The
session must complete before disbursal for loans above a configurable ceiling.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class VCIPStatus(StrEnum):
    INITIATED = "initiated"          # room created, awaiting agent + borrower join
    IN_PROGRESS = "in_progress"      # call live; capturing geotag/OVD/questions
    COMPLETED = "completed"          # all gates passed
    FAILED = "failed"                # one or more gates failed
    EXPIRED = "expired"              # session not completed before expiry
    CANCELLED = "cancelled"          # aborted by agent/borrower


class VCIPFlag(StrEnum):
    CONSENT_MISSING = "vcip_consent_missing"
    GEOTAG_MISSING = "vcip_geotag_missing"
    GEOTAG_OUTSIDE_INDIA = "vcip_geotag_outside_india"
    OVD_NOT_PRESENTED = "vcip_ovd_not_presented"
    LIVENESS_FAILED = "vcip_liveness_failed"
    FACE_MISMATCH = "vcip_face_mismatch"
    QUESTIONS_FAILED = "vcip_questions_failed"
    RECORDING_NOT_STORED = "vcip_recording_not_stored"
    SESSION_EXPIRED = "vcip_session_expired"


class VCIPGeotag(BaseModel):
    latitude: float
    longitude: float
    accuracy_m: float | None = None
    within_india: bool
    captured_at: datetime


class VCIPQuestion(BaseModel):
    question: str
    answer: str | None = None
    correct: bool | None = None


class VCIPSession(BaseModel):
    session_id: str
    application_id: str
    agent_id: str | None = None
    status: VCIPStatus = VCIPStatus.INITIATED

    # RBI: V-CIP mandatory above this loan ceiling (configurable).
    loan_amount: float
    required: bool

    # WebRTC join coordinates (opaque to the platform; signalling is external).
    room_id: str
    join_token: str

    # DPDP: explicit consent for video KYC must precede the call.
    consent_verified: bool = False

    geotag: VCIPGeotag | None = None
    ovd_type: str | None = None          # "aadhaar", "pan", "passport", "driving_licence"
    ovd_presented: bool = False
    liveness_score: float | None = None
    face_match_score: float | None = None
    questions: list[VCIPQuestion] = Field(default_factory=list)

    recording_object_id: str | None = Field(
        default=None, description="MinIO object id (bucket/object), India-region"
    )
    recording_stored: bool = False

    flags: list[VCIPFlag] = Field(default_factory=list)

    created_at: datetime
    expires_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class VCIPResult(BaseModel):
    session_id: str
    application_id: str
    status: VCIPStatus
    passed: bool
    flags: list[VCIPFlag] = Field(default_factory=list)
    recording_object_id: str | None = None
    completed_at: datetime | None = None
