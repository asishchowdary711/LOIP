"""Customer-facing demo loan-application UI.

A lightweight, self-contained onboarding experience layered on top of the
existing `/onboard` pipeline. Submissions are stored as local JSON files
(``loip/data/demo_applications/``) — no database is required for the demo
(see the demo-ui-plan). The same `OnboardingPipeline` (mock_mode) that backs
`/onboard` produces the decision shown to the applicant.
"""

import base64
import json
import logging
import os
import urllib.request
import uuid
from datetime import datetime, timezone

import cv2
import fitz
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from loip.schemas.decision import Decision, LoanApplication
from loip.web.auth import limiter
from loip.web.routes import onboard as onboard_routes
from loip.web.routes import review as review_routes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/apply", tags=["Demo UI"])

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

# Local JSON storage — demo only, no DB. Lives under the (gitignored)
# loip/data/ tree so submissions never get committed.
_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),  # loip/
    "data",
    "demo_applications",
)

def _storage_dir() -> str:
    os.makedirs(_DATA_DIR, exist_ok=True)
    return _DATA_DIR


# Real vs mock document models — auto-detected.
#
# The demo genuinely reads the UPLOADED DOCUMENTS (real OCR / field extraction /
# classification) when a local Ollama server is reachable; otherwise it falls
# back to the shared deterministic mock pipeline so the demo never breaks in
# front of an audience. Set LOIP_DEMO_REAL_MODELS=0 to force mock regardless.
#
# Only the document-intelligence stage is made real. A full mock_mode=False
# pipeline would also switch on the external bureau/identity clients
# (CIBIL/UIDAI/NSDL/DigiLocker), which have no configured endpoints; those stay
# mocked. The real pipeline is built lazily on first use and cached, and writes
# review cases into the SAME ReviewProcessor the admin UI reads (review_routes).
_OLLAMA_HOST = os.getenv("LOIP_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
_real_pipeline = None
_ollama_reachable: bool | None = None


def _real_models_active() -> bool:
    """True when uploaded files should be read by real models. Auto-detects a
    running Ollama server (cached after the first probe). LOIP_DEMO_REAL_MODELS=0
    forces mock; any other value still requires Ollama to actually be up."""
    global _ollama_reachable
    env = os.getenv("LOIP_DEMO_REAL_MODELS", "").strip().lower()
    if env in ("0", "false", "no"):
        return False
    if _ollama_reachable is None:
        try:
            with urllib.request.urlopen(f"{_OLLAMA_HOST}/api/tags", timeout=1.5) as resp:
                _ollama_reachable = resp.status == 200
        except Exception:  # noqa: BLE001 - any failure means "not reachable"
            _ollama_reachable = False
        logger.info(
            "Demo document models: %s (Ollama %s at %s)",
            "REAL" if _ollama_reachable else "MOCK",
            "reachable" if _ollama_reachable else "unreachable",
            _OLLAMA_HOST,
        )
    return _ollama_reachable


def _mode_label(real: bool) -> str:
    return "Real models — reading your documents" if real else "Mock mode — simulated extraction"


# ---------------------------------------------------------------------------
# Liveness detection via InsightFace (buffalo_l)
# ---------------------------------------------------------------------------
_face_app = None


def _get_face_app():
    global _face_app
    if _face_app is None:
        try:
            from insightface.app import FaceAnalysis

            _face_app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
            _face_app.prepare(ctx_id=-1, det_size=(320, 320))
            logger.info("InsightFace buffalo_l loaded for liveness detection")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load InsightFace: %s", exc)
    return _face_app


def _eye_aspect_ratio(landmarks_2d_106):
    """Bounding-box EAR: height/width of each eye's 10-point contour.
    InsightFace 2D-106: left eye = pts[33:43], right eye = pts[87:97].
    Open eye ≈ 0.28-0.40; closed eye ≈ 0.05-0.15 — much wider gap than
    the 6-point formula, so the 350 ms polling window is less critical."""
    pts = np.array(landmarks_2d_106)

    def bbox_ear(eye_pts):
        h = eye_pts[:, 1].max() - eye_pts[:, 1].min()
        w = eye_pts[:, 0].max() - eye_pts[:, 0].min()
        return h / (w + 1e-6)

    left_ear = bbox_ear(pts[33:43])
    right_ear = bbox_ear(pts[87:97])
    return (left_ear + right_ear) / 2.0


def _get_pipeline(real_active: bool):
    """Return the pipeline backing the demo: the shared mock pipeline, or a
    lazily-built one with real document intelligence when Ollama is reachable."""
    global _real_pipeline
    if not real_active:
        return onboard_routes.pipeline
    if _real_pipeline is None:
        from loip.domains.document_intel.processor import DocumentIntelligenceProcessor
        from loip.pipelines.onboarding import OnboardingPipeline

        logger.info("Building real-document-intelligence pipeline (external clients mocked)")
        pipeline = OnboardingPipeline(mock_mode=True)
        pipeline.doc_processor = DocumentIntelligenceProcessor(mock_mode=False)
        # Share the admin UI's review queue so customer cases appear live.
        pipeline.review_processor = review_routes.review_processor
        _real_pipeline = pipeline
    return _real_pipeline


def _extract_fields_by_class(pipeline, images: list[np.ndarray]) -> dict[str, dict]:
    """Run document classification + field extraction per image and collect the
    fields keyed by document class. Used in real mode to show "what we read" and
    to cross-check against the typed form. (Mock extraction returns canned values,
    so this is only meaningful — and only invoked — when real models are active.)"""
    by_class: dict[str, dict] = {}
    for idx, img in enumerate(images):
        try:
            logger.info("Processing document index %d: shape=%s", idx, img.shape)
            result = pipeline.doc_processor.process(img)
            doc_class = result["classification"].document_class.value
            logger.info("Document index %d classified as: %s (confidence=%.2f)", idx, doc_class, result["classification"].confidence)
            fields = {f.name: f.value for f in result["extraction"].fields}
            logger.info("Document index %d extracted fields: %s", idx, fields)
            by_class[doc_class] = fields
        except Exception as exc:  # noqa: BLE001
            logger.warning("Extraction pass failed for document index %d: %s", idx, exc)
    return by_class


def _normalize(value) -> str:
    return "".join(str(value).split()).upper()


def _cross_check(form: dict, extracted: dict[str, dict]) -> list[str]:
    """Compare typed PAN / Aadhaar numbers against what the models read from the
    uploaded documents. Returns human-readable mismatch messages."""
    mismatches: list[str] = []
    typed_pan = _normalize(form.get("pan_number", ""))
    read_pan = _normalize(extracted.get("pan", {}).get("pan_number", ""))
    if typed_pan:
        if not read_pan:
            mismatches.append("Could not extract PAN number from the uploaded PAN document.")
        elif typed_pan != read_pan:
            mismatches.append(f"PAN on document ({read_pan}) does not match the PAN you entered ({typed_pan}).")

    typed_aadhaar = _normalize(form.get("aadhaar_number", "")).replace("-", "")
    read_aadhaar = _normalize(extracted.get("aadhaar", {}).get("aadhaar_number", "")).replace("-", "")
    if typed_aadhaar:
        if not read_aadhaar:
            mismatches.append("Could not extract Aadhaar number from the uploaded Aadhaar document.")
        elif typed_aadhaar != read_aadhaar:
            mismatches.append(f"Aadhaar number on document ({read_aadhaar}) does not match the number you entered ({typed_aadhaar}).")
    return mismatches


@router.get("", response_class=HTMLResponse)
async def apply_page(request: Request):
    return templates.TemplateResponse(request=request, name="apply.html", context={})


@router.get("/mode")
async def current_mode():
    """Active document-model mode, so the UI can show a Real/Mock banner."""
    real = _real_models_active()
    return {"real_models": real, "mode_label": _mode_label(real)}


@router.get("/liveness/warmup")
async def liveness_warmup():
    """Eagerly load InsightFace buffalo_l so the first webcam frame doesn't pay
    the cold-start cost. Called by start-demo.sh after the backend is ready."""
    app = _get_face_app()
    return {"ready": app is not None}


@router.post("/liveness")
async def liveness_check(request: Request):
    """Receive a base64-encoded webcam frame, run InsightFace face analysis,
    and return head yaw angle + eye-aspect-ratio for the frontend liveness
    challenge (turn right, turn left, blink)."""
    body = await request.json()
    frame_b64 = body.get("frame", "")
    if not frame_b64:
        return JSONResponse({"face": False, "error": "no frame"})

    if "," in frame_b64:
        frame_b64 = frame_b64.split(",", 1)[1]

    try:
        raw = base64.b64decode(frame_b64)
        nparr = np.frombuffer(raw, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except Exception:
        return JSONResponse({"face": False, "error": "decode failed"})

    if img is None:
        return JSONResponse({"face": False, "error": "invalid image"})

    app = _get_face_app()
    if app is None:
        return JSONResponse({"face": False, "error": "insightface not available"})

    faces = app.get(img)
    if not faces:
        return JSONResponse({"face": False, "yaw": 0, "ear": 0.3})

    face = faces[0]

    yaw = 0.0
    if hasattr(face, "pose") and face.pose is not None:
        yaw = float(face.pose[1])
    elif hasattr(face, "embedding"):
        yaw = 0.0

    ear = 0.3
    if hasattr(face, "landmark_2d_106") and face.landmark_2d_106 is not None:
        ear = float(_eye_aspect_ratio(face.landmark_2d_106))

    return JSONResponse({
        "face": True,
        "yaw": round(yaw, 1),
        "ear": round(ear, 3),
    })


@router.get("/status/{application_id}", response_class=HTMLResponse)
async def status_page(request: Request, application_id: str):
    """Customer status page. Shows the stored submission and the current
    decision, merging any later action the bank admin took on the case."""
    path = os.path.join(_storage_dir(), f"{application_id}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            record = json.load(fh)
    else:
        case = review_routes.review_processor.get_case_by_application(application_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Application not found")
        
        decision = case.onboarding_decision
        decision_payload = {}
        if decision:
            if hasattr(decision, "model_dump"):
                decision_payload = decision.model_dump(mode="json")
            else:
                decision_payload = dict(decision)
        
        record = {
            "application_id": case.application_id,
            "submitted_at": case.created_at.isoformat() if case.created_at else datetime.now(timezone.utc).isoformat(),
            "form": {
                "full_name": case.applicant_name,
                "mobile_number": "",
                "pan_number": "",
                "aadhaar_number": "",
                "employment_type": (decision.income_result.segment if (decision and decision.income_result) else "salaried"),
                "monthly_income": (decision.income_result.verified_monthly_income if (decision and decision.income_result) else 0.0),
                "loan_amount": case.loan_amount,
            },
            "real_models": False,
            "mode_label": "Mock mode",
            "documents": [],
            "dropped_documents": [],
            "extracted_fields": {},
            "mismatches": case.review_flags,
            "decision": decision_payload or {
                "application_id": case.application_id,
                "decision": case.system_decision.value,
                "loan_amount": case.loan_amount,
                "reason_codes": [],
                "risk_score": case.risk_score,
                "review_flags": case.review_flags,
                "disbursal_blocked": False,
                "disbursal_block_reason": None,
            }
        }

    system_decision = (record.get("decision") or {}).get("decision", "review")
    final_decision = system_decision
    review_status = None
    override = None
    case = review_routes.review_processor.get_case_by_application(application_id)
    if case is not None:
        review_status = case.status.value
        overrides = review_routes.review_processor.get_overrides(application_id)
        if overrides:
            override = overrides[-1]
            final_decision = override.override_decision.value

    return templates.TemplateResponse(
        request=request,
        name="status.html",
        context={
            "record": record,
            "application_id": application_id,
            "system_decision": system_decision,
            "final_decision": final_decision,
            "review_status": review_status,
            "override": override,
        },
    )


@router.post("/submit")
@limiter.limit("10/minute")
async def submit_application(
    request: Request,
    full_name: str = Form(...),
    mobile_number: str = Form(...),
    pan_number: str = Form(...),
    aadhaar_number: str = Form(...),
    employment_type: str = Form(...),
    monthly_income: float = Form(...),
    loan_amount: float = Form(...),
    documents: list[UploadFile] = File(...),
):
    application_id = f"demo_{uuid.uuid4().hex[:10]}"

    # Map the 7 demo fields onto the real LoanApplication. tenure_months and
    # employment_tier aren't collected in the trimmed demo form, so they take
    # sensible defaults (24 months, tier 3 = large private).
    try:
        loan_app = LoanApplication(
            application_id=application_id,
            applicant_name=full_name.strip(),
            loan_amount=loan_amount,
            tenure_months=24,
            employment_type=employment_type,
            employment_tier=3,
            declared_monthly_income=monthly_income,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid application data: {exc}")

    images: list[np.ndarray] = []
    raw_documents: list[bytes] = []
    accepted_documents: list[str] = []
    dropped_documents: list[str] = []
    for doc in documents:
        contents = await doc.read()
        filename = doc.filename or "unknown"
        is_pdf = (
            filename.lower().endswith(".pdf")
            or doc.content_type == "application/pdf"
            or contents[:5] == b"%PDF-"
        )
        if is_pdf:
            try:
                pdf = fitz.open(stream=contents, filetype="pdf")
                for page in pdf:
                    pix = page.get_pixmap(dpi=200)
                    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                        pix.h, pix.w, pix.n
                    )
                    if pix.n == 4:
                        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
                    else:
                        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                    images.append(img_bgr)
                    raw_documents.append(contents)
                    accepted_documents.append(f"{filename} (p{page.number + 1})")
                pdf.close()
            except Exception:
                logger.warning("Could not parse PDF: %s", filename)
                dropped_documents.append(filename)
        else:
            nparr = np.frombuffer(contents, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is not None:
                images.append(img)
                raw_documents.append(contents)
                accepted_documents.append(filename)
            else:
                dropped_documents.append(filename)

    if not images:
        raise HTTPException(status_code=400, detail="No valid document images provided")

    real_active = _real_models_active()
    pipeline = _get_pipeline(real_active)

    form = {
        "full_name": full_name.strip(),
        "mobile_number": mobile_number.strip(),
        "pan_number": pan_number.strip().upper(),
        "aadhaar_number": aadhaar_number.strip(),
        "employment_type": employment_type,
        "monthly_income": monthly_income,
        "loan_amount": loan_amount,
    }

    app_data = {
        "application_id": application_id,
        "applicant_name": full_name.strip(),
        "loan_amount": loan_amount,
        "tenure_months": 24,
        "employment_type": employment_type,
        "employment_tier": 3,
        "declared_monthly_income": monthly_income,
    }
    # In real mode the models read the actual name off the document, so the
    # typed name is a meaningful cross-check (the identity processor's BGE-M3
    # name match reads application_data["full_name"]). In mock mode extraction
    # returns canned values, so feeding the typed name would falsely mismatch —
    # we leave it out to preserve the deterministic mock path.
    if real_active:
        app_data["full_name"] = full_name.strip()

    # "What we read" + typed-vs-extracted cross-check, real mode only.
    extracted_fields: dict[str, dict] = {}
    mismatches: list[str] = []
    if real_active:
        extracted_fields = _extract_fields_by_class(pipeline, images)
        mismatches = _cross_check(form, extracted_fields)

    try:
        decision = await pipeline.execute(
            loan_app,
            images,
            app_data,
            raw_documents=raw_documents,
            document_store=onboard_routes.document_store,
            event_publisher=onboard_routes.event_publisher,
            identity_graph=onboard_routes.identity_graph,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}")

    # A mismatch between the uploaded document and the typed form must not sail
    # through as an approval — downgrade to REVIEW and surface the reason.
    if mismatches:
        decision.review_flags = list(decision.review_flags) + mismatches
        if decision.decision == Decision.APPROVE:
            decision.decision = Decision.REVIEW

    # Make sure the case is in the admin queue and labelled with the real name.
    # The pipeline already enqueues review/reject cases on the shared processor;
    # if a downgrade created a new REVIEW we may need to enqueue it ourselves.
    if decision.decision in (Decision.REVIEW, Decision.REJECT):
        case = review_routes.review_processor.get_case_by_application(application_id)
        if case is None:
            case = review_routes.review_processor.create_review_case(decision)
        case.applicant_name = full_name.strip()

    decision_payload = decision.model_dump(mode="json")

    record = {
        "application_id": application_id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "form": form,
        "real_models": real_active,
        "mode_label": _mode_label(real_active),
        "documents": accepted_documents,
        "dropped_documents": dropped_documents,
        "extracted_fields": extracted_fields,
        "mismatches": mismatches,
        "decision": decision_payload,
    }

    out_path = os.path.join(_storage_dir(), f"{application_id}.json")
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, default=str)
    except OSError as exc:
        logger.warning("Could not persist demo application %s: %s", application_id, exc)

    return JSONResponse(
        {
            "application_id": application_id,
            "decision": decision_payload.get("decision"),
            "risk_score": decision_payload.get("risk_score"),
            "loan_amount": decision_payload.get("loan_amount"),
            "reason_codes": decision_payload.get("reason_codes", []),
            "review_flags": decision_payload.get("review_flags", []),
            "documents_processed": accepted_documents,
            "documents_dropped": dropped_documents,
            "extracted_fields": extracted_fields,
            "mismatches": mismatches,
            "real_models": real_active,
            "mode_label": _mode_label(real_active),
            "stored_at": f"data/demo_applications/{application_id}.json",
            "status_url": f"/apply/status/{application_id}",
        }
    )
