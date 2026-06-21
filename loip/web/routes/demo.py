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
from loip.services.eligibility import calculate_eligibility
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
        from loip.domains.identity_trust.processor import IdentityTrustProcessor
        from loip.domains.income_intel.processor import IncomeIntelligenceProcessor
        from loip.domains.affordability.processor import AffordabilityProcessor
        from loip.domains.fraud.processor import FraudIntelligenceProcessor
        from loip.domains.risk_decisioning.processor import RiskDecisionProcessor
        from loip.pipelines.onboarding import OnboardingPipeline

        logger.info("Building real ML pipeline (external bureau/identity clients still mocked)")
        pipeline = OnboardingPipeline(mock_mode=True)
        pipeline.doc_processor = DocumentIntelligenceProcessor(mock_mode=False)

        # Real ML inference: BGE-M3 name matching, XGBoost/LightGBM/GraphSAGE
        # scoring. External API clients (CIBIL/UIDAI/NSDL/DigiLocker) have no
        # real endpoints configured, so we keep their .mock toggles on while
        # the ML wrappers run in real mode.
        identity = IdentityTrustProcessor(mock_mode=False)
        identity.nsdl_client._mock = True
        identity.uidai_client._mock = True
        pipeline.identity_processor = identity
        pipeline.income_processor = IncomeIntelligenceProcessor(mock_mode=False)
        pipeline.affordability_processor = AffordabilityProcessor(mock_mode=False)
        pipeline.fraud_processor = FraudIntelligenceProcessor(mock_mode=False)
        pipeline.decision_processor = RiskDecisionProcessor(mock_mode=False)
        # CIBIL bureau client stays mocked (no real endpoint).
        pipeline.cibil_client._mock = True
        # Share the admin UI's review queue so customer cases appear live.
        pipeline.review_processor = review_routes.review_processor
        _real_pipeline = pipeline
    return _real_pipeline


async def _extract_fields_by_class(
    pipeline, images: list[np.ndarray]
) -> tuple[dict[str, dict], list[str]]:
    """Run document classification + field extraction per image, concurrently.

    Each Qwen call is a network round-trip to Ollama; running them in
    parallel collapses the wall-clock cost from N×per-doc to ~per-doc.
    Returns:
    - by_class: per-document-class structured fields (what the VL model parsed)
    - ocr_texts: raw OCR text for every uploaded document (used as a fallback
      when the VL model misses a field — we substring-search the typed PAN /
      Aadhaar / name against the concatenated OCR of all docs).
    """
    import asyncio as _asyncio

    by_class: dict[str, dict] = {}
    ocr_texts: list[str] = []

    async def _process_one(idx: int, img):
        logger.info("Processing document index %d: shape=%s", idx, img.shape)
        try:
            return idx, await _asyncio.to_thread(pipeline.doc_processor.process, img)
        except Exception as exc:  # noqa: BLE001 - logged, treated as empty below
            logger.warning("Extraction pass failed for document index %d: %s", idx, exc)
            return idx, None

    results = await _asyncio.gather(*(_process_one(i, img) for i, img in enumerate(images)))

    for idx, result in results:
        try:
            if result is None:
                ocr_texts.append("")
                continue
            doc_class = result["classification"].document_class.value
            logger.info("Document index %d classified as: %s (confidence=%.2f)", idx, doc_class, result["classification"].confidence)
            fields = {f.name: f.value for f in result["extraction"].fields}
            logger.info("Document index %d extracted fields: %s", idx, fields)
            by_class[doc_class] = fields

            # Pull raw OCR text from whichever OCR engine the pipeline used.
            ocr = result.get("ocr")
            raw_text = ""
            if ocr is not None:
                raw_text = getattr(ocr, "raw_text", "") or ""
                # OCRConflict (primary vs secondary disagree) exposes both;
                # join them so the fallback search sees as much text as possible.
                if not raw_text:
                    for attr in ("primary", "secondary"):
                        sub = getattr(ocr, attr, None)
                        if sub is not None:
                            raw_text += " " + (getattr(sub, "raw_text", "") or "")
            ocr_texts.append(raw_text)
            if raw_text:
                logger.info("Document index %d OCR raw text (%d chars): %s",
                            idx, len(raw_text), raw_text[:200].replace("\n", " "))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Extraction pass failed for document index %d: %s", idx, exc)
            ocr_texts.append("")
    return by_class, ocr_texts


def _normalize(value) -> str:
    return "".join(str(value).split()).upper()


def _ocr_contains(ocr_texts: list[str], needle: str) -> bool:
    """Substring search across all uploaded documents' OCR text. Spaces,
    dashes, and case are ignored so '3042 8897 1384' matches '304288971384'."""
    if not needle:
        return False
    needle = _normalize(needle).replace("-", "")
    for text in ocr_texts:
        if not text:
            continue
        haystack = _normalize(text).replace("-", "")
        if needle in haystack:
            return True
    return False


def _cross_check(
    form: dict,
    extracted: dict[str, dict],
    ocr_texts: list[str] | None = None,
) -> list[str]:
    """Compare typed PAN / Aadhaar numbers against what the models read from the
    uploaded documents. If the structured VL extraction misses a field, fall back
    to substring-matching the typed value against the raw OCR text of every doc
    (PaddleOCR / Surya pull text even when the VL model fails to label it).
    Returns human-readable mismatch messages."""
    ocr_texts = ocr_texts or []
    mismatches: list[str] = []

    typed_pan = _normalize(form.get("pan_number", ""))
    read_pan = _normalize(extracted.get("pan", {}).get("pan_number", ""))
    if typed_pan:
        if read_pan:
            if typed_pan != read_pan:
                mismatches.append(f"PAN on document ({read_pan}) does not match the PAN you entered ({typed_pan}).")
        elif _ocr_contains(ocr_texts, typed_pan):
            logger.info("PAN %s found via OCR-text fallback (VL extraction missed it)", typed_pan)
        else:
            mismatches.append("Could not find your PAN number anywhere in the uploaded documents.")

    typed_aadhaar = _normalize(form.get("aadhaar_number", "")).replace("-", "")
    read_aadhaar = _normalize(extracted.get("aadhaar", {}).get("aadhaar_number", "")).replace("-", "")
    if typed_aadhaar:
        if read_aadhaar:
            if typed_aadhaar != read_aadhaar:
                mismatches.append(f"Aadhaar number on document ({read_aadhaar}) does not match the number you entered ({typed_aadhaar}).")
        elif _ocr_contains(ocr_texts, typed_aadhaar):
            logger.info("Aadhaar %s found via OCR-text fallback (VL extraction missed it)", typed_aadhaar)
        else:
            mismatches.append("Could not find your Aadhaar number anywhere in the uploaded documents.")

    # Name cross-check — the typed name's longest token (likely the surname)
    # must appear somewhere we read it. Check both:
    #   (a) raw OCR text across all docs (PaddleOCR / Surya), and
    #   (b) the structured name fields Qwen extracted per doc class.
    # The OCR path is unreliable here (PaddleOCR mocks out on Python 3.14, so
    # raw OCR text is just "MOCK_TEXT") — without the structured fallback the
    # check would falsely flag every real submission.
    typed_name = (form.get("full_name") or "").strip()
    if typed_name:
        tokens = [t for t in typed_name.split() if len(t) >= 3]
        if tokens:
            longest = max(tokens, key=len).upper()
            extracted_name_blob = " ".join(
                str(v) for doc in extracted.values()
                for k, v in (doc or {}).items()
                if k in {"full_name", "employee_name", "account_holder_name",
                         "fathers_name", "applicant_name"} and v
            ).upper()
            in_ocr = _ocr_contains(ocr_texts, longest) if ocr_texts else False
            in_fields = longest in extracted_name_blob
            if not in_ocr and not in_fields:
                mismatches.append(
                    f"Your name ({typed_name}) does not appear in any uploaded document. "
                    "Please ensure the documents belong to the applicant."
                )

    # Income cross-check — the typed monthly income must agree with what the
    # pay slip shows (and, when available, with the bank statement's salary
    # credits). 10% tolerance covers HRA/bonus/round-off; anything beyond that
    # is flagged so a fabricated income on the form cannot sail through.
    typed_income = _to_float(form.get("monthly_income"))
    if typed_income > 0:
        slip = extracted.get("salary_slip", {}) or {}
        slip_net = _to_float(slip.get("net_pay")) or _to_float(slip.get("gross_pay"))
        if slip_net > 0:
            delta = abs(typed_income - slip_net) / max(typed_income, slip_net)
            if delta > 0.10:
                direction = "higher" if typed_income > slip_net else "lower"
                mismatches.append(
                    f"Declared income ₹{typed_income:,.0f} is {direction} than the pay slip "
                    f"net pay (₹{slip_net:,.0f}) by {delta*100:.0f}%."
                )

        bank = extracted.get("bank_statement", {}) or {}
        bank_credits = bank.get("salary_credits") or []
        if bank_credits:
            amounts = [_to_float(c.get("amount")) for c in bank_credits if _to_float(c.get("amount")) > 0]
            if amounts:
                bank_avg = sum(amounts) / len(amounts)
                delta_bank = abs(typed_income - bank_avg) / max(typed_income, bank_avg)
                if delta_bank > 0.10:
                    direction = "higher" if typed_income > bank_avg else "lower"
                    mismatches.append(
                        f"Declared income ₹{typed_income:,.0f} is {direction} than the bank "
                        f"statement's average salary credit (₹{bank_avg:,.0f}) by {delta_bank*100:.0f}%."
                    )
    return mismatches


def _to_float(value) -> float:
    """Parse a numeric value that may be a string with commas / lakh notation.
    Returns 0.0 when the value cannot be interpreted as a positive number."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(",", "").replace("₹", "").replace(" ", "")
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


@router.get("", response_class=HTMLResponse)
async def apply_page(request: Request):
    return templates.TemplateResponse(request=request, name="apply.html", context={})


@router.get("/mode")
async def current_mode():
    """Active document-model mode, so the UI can show a Real/Mock banner."""
    real = _real_models_active()
    return {"real_models": real, "mode_label": _mode_label(real)}


@router.post("/_reset_fraud_graph")
async def reset_fraud_graph():
    """Clear the in-memory GraphSAGE application graph. Same applicant
    re-submitting the same PAN/Aadhaar across many demo runs would otherwise
    accumulate as a self-match and inflate fraud_score over time. Restarting
    the server clears this too — this endpoint just lets you do it without
    a restart."""
    global _real_pipeline
    cleared = 0
    if _real_pipeline is not None:
        try:
            cleared = _real_pipeline.fraud_processor.graphsage.reset_graph()
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    return JSONResponse({"ok": True, "cleared_nodes": cleared})


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
        extracted_fields, ocr_texts = await _extract_fields_by_class(pipeline, images)
        mismatches = _cross_check(form, extracted_fields, ocr_texts=ocr_texts)

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

    # Surface the structured per-domain signals so the UI can label rows
    # precisely (e.g. show "Possible tampering" on PAN ONLY when an actual
    # document tamper flag fires, not whenever the word "fraud" appears
    # anywhere in the reason codes).
    identity_payload = decision_payload.get("identity_result") or {}
    income_payload = decision_payload.get("income_result") or {}
    fraud_payload = decision_payload.get("fraud_result") or {}

    return JSONResponse(
        {
            "application_id": application_id,
            "decision": decision_payload.get("decision"),
            "risk_score": decision_payload.get("risk_score"),
            "loan_amount": decision_payload.get("loan_amount"),
            "reason_codes": decision_payload.get("reason_codes", []),
            "review_flags": decision_payload.get("review_flags", []),
            "identity_tamper_flags": identity_payload.get("tamper_flags") or [],
            "income_anomaly_flags": income_payload.get("anomaly_flags") or [],
            "fraud_score": fraud_payload.get("fraud_score"),
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


@router.get("/eligibility")
async def loan_eligibility(salary: int):
    try:
        result = calculate_eligibility(salary)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return JSONResponse(result)
