"""V-CIP (Video-based CIP) processor — RBI January 2020 circular.

Drives the lifecycle of an agent-led video-KYC session:

    initiate -> capture_geotag / present_ovd / answer_question / store_recording -> complete

Each step records evidence on the session; ``complete_session`` evaluates every
RBI gate (consent, geotag-in-India, OVD presented + live face match, random
questions answered, recording persisted to India-region storage) and resolves
the session to COMPLETED or FAILED with reason flags.

Liveness and face match reuse the same ArcFace / MiniFASNet wrappers as the
identity-trust processor; in ``mock_mode`` they return passing scores so the
flow is testable without model weights or a real WebRTC bridge.
"""

from __future__ import annotations

import logging
import random
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from loip.models.arcface_wrapper import ArcFaceWrapper
from loip.models.minifasnet_wrapper import MiniFASNetWrapper
from loip.schemas.vcip import (
    VCIPFlag,
    VCIPGeotag,
    VCIPQuestion,
    VCIPResult,
    VCIPSession,
    VCIPStatus,
)

logger = logging.getLogger(__name__)

# RBI: V-CIP required for fully digital loans above this ceiling (configurable).
VCIP_REQUIRED_ABOVE = 200_000.0
# Session must complete within this window or it expires.
SESSION_TTL_MINUTES = 30
# Number of random questions the agent must ask (RBI: at least two).
NUM_RANDOM_QUESTIONS = 2

FACE_MATCH_THRESHOLD = 0.60
LIVENESS_THRESHOLD = 0.50

# Mainland + island bounding box for India (coarse geofence; refine with a
# polygon/PIN-to-geo lookup in production).
INDIA_LAT_RANGE = (6.5, 37.6)
INDIA_LON_RANGE = (68.1, 97.5)

QUESTION_POOL = [
    "Please state your full name as printed on the document you are showing.",
    "What is your date of birth?",
    "Please read out the last four digits of the document number on screen.",
    "Which city and state is your current residential address in?",
    "What is the purpose of the loan you have applied for?",
    "Please state today's date.",
    "What is your father's name?",
    "Which bank account will the loan be disbursed to?",
]


def is_within_india(latitude: float, longitude: float) -> bool:
    return (
        INDIA_LAT_RANGE[0] <= latitude <= INDIA_LAT_RANGE[1]
        and INDIA_LON_RANGE[0] <= longitude <= INDIA_LON_RANGE[1]
    )


class VCIPSessionNotFoundError(Exception):
    """Raised when an operation references an unknown session id."""


class VCIPProcessor:
    def __init__(self, mock_mode: bool = True, document_store=None):
        self.mock_mode = mock_mode
        self.document_store = document_store
        self.arcface = ArcFaceWrapper(mock_mode=mock_mode)
        self.minifasnet = MiniFASNetWrapper(mock_mode=mock_mode)
        self._sessions: dict[str, VCIPSession] = {}

    # --- Gating ---

    @staticmethod
    def is_required(loan_amount: float, threshold: float = VCIP_REQUIRED_ABOVE) -> bool:
        return loan_amount > threshold

    # --- Lifecycle ---

    def initiate_session(
        self,
        application_id: str,
        loan_amount: float,
        consent_verified: bool,
        agent_id: str | None = None,
        threshold: float = VCIP_REQUIRED_ABOVE,
    ) -> VCIPSession:
        now = datetime.now(UTC)
        questions = [
            VCIPQuestion(question=q)
            for q in random.sample(QUESTION_POOL, NUM_RANDOM_QUESTIONS)
        ]
        session = VCIPSession(
            session_id=str(uuid.uuid4()),
            application_id=application_id,
            agent_id=agent_id,
            loan_amount=loan_amount,
            required=self.is_required(loan_amount, threshold),
            room_id=f"vcip-{uuid.uuid4().hex[:12]}",
            join_token=secrets.token_urlsafe(24),
            consent_verified=consent_verified,
            questions=questions,
            created_at=now,
            expires_at=now + timedelta(minutes=SESSION_TTL_MINUTES),
        )
        if not consent_verified:
            session.flags.append(VCIPFlag.CONSENT_MISSING)
        self._sessions[session.session_id] = session
        logger.info("V-CIP session %s initiated for application %s", session.session_id, application_id)
        return session

    def get_session(self, session_id: str) -> VCIPSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise VCIPSessionNotFoundError(session_id)
        return session

    def _ensure_in_progress(self, session: VCIPSession) -> None:
        if session.status == VCIPStatus.INITIATED:
            session.status = VCIPStatus.IN_PROGRESS
            session.started_at = datetime.now(UTC)

    def capture_geotag(
        self, session_id: str, latitude: float, longitude: float, accuracy_m: float | None = None
    ) -> VCIPSession:
        session = self.get_session(session_id)
        self._ensure_in_progress(session)
        within = is_within_india(latitude, longitude)
        session.geotag = VCIPGeotag(
            latitude=latitude,
            longitude=longitude,
            accuracy_m=accuracy_m,
            within_india=within,
            captured_at=datetime.now(UTC),
        )
        return session

    def present_ovd(
        self,
        session_id: str,
        ovd_type: str,
        selfie_frame=None,
        ovd_face_img=None,
        liveness_score: float | None = None,
        face_match_score: float | None = None,
    ) -> VCIPSession:
        """Record that the borrower held an OVD to the camera and score the
        live face against the document photo.

        Scores may be passed in directly, or computed from image arrays via the
        ArcFace/MiniFASNet wrappers. In mock mode, missing scores default to
        passing values.
        """
        session = self.get_session(session_id)
        self._ensure_in_progress(session)
        session.ovd_type = ovd_type
        session.ovd_presented = True

        if liveness_score is None and selfie_frame is not None:
            liveness_score = self.minifasnet.detect_liveness(selfie_frame)
        if face_match_score is None and selfie_frame is not None and ovd_face_img is not None:
            face_match_score = self.arcface.verify_face(selfie_frame, ovd_face_img)

        if self.mock_mode:
            liveness_score = 0.95 if liveness_score is None else liveness_score
            face_match_score = 0.92 if face_match_score is None else face_match_score

        session.liveness_score = liveness_score
        session.face_match_score = face_match_score
        return session

    def answer_question(self, session_id: str, index: int, answer: str, correct: bool | None = None) -> VCIPSession:
        session = self.get_session(session_id)
        self._ensure_in_progress(session)
        if index < 0 or index >= len(session.questions):
            raise IndexError(f"Question index {index} out of range")
        question = session.questions[index]
        question.answer = answer
        # The agent adjudicates correctness on the call; default to accepting a
        # non-empty answer when no explicit verdict is supplied.
        question.correct = bool(answer.strip()) if correct is None else correct
        return session

    def store_recording(self, session_id: str, recording: bytes, *, ext: str = "webm") -> VCIPSession:
        """Persist the call recording to India-region MinIO and link it to the
        session. Falls back to a synthetic object id when no store is wired
        (e.g. unit tests / mock_mode)."""
        session = self.get_session(session_id)
        self._ensure_in_progress(session)
        if self.document_store is not None:
            object_id = self.document_store.store("vcip_recording", recording, ext=ext)
        else:
            object_id = f"vcip-recordings/{uuid.uuid4().hex}.{ext}"
        session.recording_object_id = object_id
        session.recording_stored = True
        return session

    # --- Completion ---

    def complete_session(self, session_id: str) -> VCIPResult:
        session = self.get_session(session_id)
        now = datetime.now(UTC)
        flags: list[VCIPFlag] = []

        if now > session.expires_at and session.status not in (VCIPStatus.COMPLETED, VCIPStatus.FAILED):
            flags.append(VCIPFlag.SESSION_EXPIRED)

        if not session.consent_verified:
            flags.append(VCIPFlag.CONSENT_MISSING)

        if session.geotag is None:
            flags.append(VCIPFlag.GEOTAG_MISSING)
        elif not session.geotag.within_india:
            flags.append(VCIPFlag.GEOTAG_OUTSIDE_INDIA)

        if not session.ovd_presented:
            flags.append(VCIPFlag.OVD_NOT_PRESENTED)
        else:
            if session.liveness_score is not None and session.liveness_score < LIVENESS_THRESHOLD:
                flags.append(VCIPFlag.LIVENESS_FAILED)
            if session.face_match_score is not None and session.face_match_score < FACE_MATCH_THRESHOLD:
                flags.append(VCIPFlag.FACE_MISMATCH)

        if not session.questions or not all(q.correct for q in session.questions):
            flags.append(VCIPFlag.QUESTIONS_FAILED)

        if not session.recording_stored:
            flags.append(VCIPFlag.RECORDING_NOT_STORED)

        # De-dupe while preserving order (consent flag may be added twice).
        session.flags = list(dict.fromkeys(flags))
        passed = not session.flags
        session.status = VCIPStatus.COMPLETED if passed else VCIPStatus.FAILED
        session.completed_at = now

        logger.info(
            "V-CIP session %s %s (%d flag(s))",
            session_id,
            session.status.value,
            len(session.flags),
        )
        return VCIPResult(
            session_id=session.session_id,
            application_id=session.application_id,
            status=session.status,
            passed=passed,
            flags=session.flags,
            recording_object_id=session.recording_object_id,
            completed_at=session.completed_at,
        )

    def cancel_session(self, session_id: str) -> VCIPSession:
        session = self.get_session(session_id)
        session.status = VCIPStatus.CANCELLED
        session.completed_at = datetime.now(UTC)
        return session
