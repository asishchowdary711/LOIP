"""V-CIP processor tests — RBI January 2020 video-KYC gates."""

from loip.domains.identity_trust.vcip import (
    VCIP_REQUIRED_ABOVE,
    VCIPProcessor,
    is_within_india,
)
from loip.schemas.vcip import VCIPFlag, VCIPStatus

# Mumbai-ish coordinates (inside India) and London (outside).
INSIDE = (19.07, 72.87)
OUTSIDE = (51.50, -0.12)


def _full_happy_session(proc: VCIPProcessor, loan_amount: float = 500_000):
    session = proc.initiate_session(
        application_id="app-1", loan_amount=loan_amount, consent_verified=True
    )
    sid = session.session_id
    proc.capture_geotag(sid, *INSIDE)
    proc.present_ovd(sid, ovd_type="aadhaar")
    for i in range(len(session.questions)):
        proc.answer_question(sid, i, "a valid answer", correct=True)
    proc.store_recording(sid, b"fake-webm-bytes")
    return sid


def test_required_threshold():
    assert VCIPProcessor.is_required(VCIP_REQUIRED_ABOVE + 1) is True
    assert VCIPProcessor.is_required(VCIP_REQUIRED_ABOVE) is False
    assert VCIPProcessor.is_required(150_000) is False


def test_geofence():
    assert is_within_india(*INSIDE) is True
    assert is_within_india(*OUTSIDE) is False


def test_happy_path_completes():
    proc = VCIPProcessor(mock_mode=True)
    sid = _full_happy_session(proc)
    result = proc.complete_session(sid)
    assert result.passed is True
    assert result.status == VCIPStatus.COMPLETED
    assert result.flags == []
    assert result.recording_object_id is not None


def test_missing_consent_flags_and_fails():
    proc = VCIPProcessor(mock_mode=True)
    session = proc.initiate_session(
        application_id="app-2", loan_amount=500_000, consent_verified=False
    )
    assert VCIPFlag.CONSENT_MISSING in session.flags
    result = proc.complete_session(session.session_id)
    assert result.passed is False
    assert VCIPFlag.CONSENT_MISSING in result.flags


def test_geotag_outside_india_fails():
    proc = VCIPProcessor(mock_mode=True)
    session = proc.initiate_session(
        application_id="app-3", loan_amount=500_000, consent_verified=True
    )
    sid = session.session_id
    proc.capture_geotag(sid, *OUTSIDE)
    proc.present_ovd(sid, ovd_type="aadhaar")
    for i in range(len(session.questions)):
        proc.answer_question(sid, i, "ok", correct=True)
    proc.store_recording(sid, b"x")
    result = proc.complete_session(sid)
    assert result.passed is False
    assert VCIPFlag.GEOTAG_OUTSIDE_INDIA in result.flags


def test_low_face_match_fails():
    proc = VCIPProcessor(mock_mode=True)
    session = proc.initiate_session(
        application_id="app-4", loan_amount=500_000, consent_verified=True
    )
    sid = session.session_id
    proc.capture_geotag(sid, *INSIDE)
    proc.present_ovd(sid, ovd_type="pan", liveness_score=0.9, face_match_score=0.3)
    for i in range(len(session.questions)):
        proc.answer_question(sid, i, "ok", correct=True)
    proc.store_recording(sid, b"x")
    result = proc.complete_session(sid)
    assert VCIPFlag.FACE_MISMATCH in result.flags
    assert result.passed is False


def test_unanswered_questions_fail():
    proc = VCIPProcessor(mock_mode=True)
    sid = _full_happy_session(proc)
    # Override one answer to incorrect.
    session = proc.get_session(sid)
    session.questions[0].correct = False
    result = proc.complete_session(sid)
    assert VCIPFlag.QUESTIONS_FAILED in result.flags


def test_missing_recording_fails():
    proc = VCIPProcessor(mock_mode=True)
    session = proc.initiate_session(
        application_id="app-5", loan_amount=500_000, consent_verified=True
    )
    sid = session.session_id
    proc.capture_geotag(sid, *INSIDE)
    proc.present_ovd(sid, ovd_type="aadhaar")
    for i in range(len(session.questions)):
        proc.answer_question(sid, i, "ok", correct=True)
    result = proc.complete_session(sid)
    assert VCIPFlag.RECORDING_NOT_STORED in result.flags
