"""Customer-facing demo loan-application UI.

A lightweight, self-contained onboarding experience layered on top of the
existing `/onboard` pipeline. Submissions are stored as local JSON files
(``loip/data/demo_applications/``) — no database is required for the demo
(see the demo-ui-plan). The same `OnboardingPipeline` (mock_mode) that backs
`/onboard` produces the decision shown to the applicant.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from loip.schemas.decision import LoanApplication
from loip.web.auth import limiter
from loip.web.routes import onboard as onboard_routes

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


# Real-model toggle. By default the demo reuses the shared mock-mode pipeline
# (deterministic, no weights, fast — right for CI and cheap demos). Set
# LOIP_DEMO_REAL_MODELS=1 to genuinely read the UPLOADED DOCUMENTS with real
# OCR / field-extraction / classification.
#
# We deliberately only make the document-intelligence stage real. A full
# mock_mode=False pipeline would ALSO switch on the external bureau/identity
# clients (CIBIL/UIDAI/NSDL/DigiLocker), which have no configured endpoints and
# fail with "Request URL is missing an 'http://' protocol". Those stages stay
# mocked; only document reading is real. Any document wrapper whose deps are
# missing falls back to mock via its own ImportError guard (e.g. Qwen uses the
# local Ollama backend). The pipeline is built lazily on first use and cached.
_REAL_MODELS = os.getenv("LOIP_DEMO_REAL_MODELS", "0").lower() in ("1", "true", "yes")
_real_pipeline = None


def _get_pipeline():
    """Return the pipeline backing the demo: the shared mock pipeline, or a
    lazily-built one with real document intelligence when
    LOIP_DEMO_REAL_MODELS is set."""
    global _real_pipeline
    if not _REAL_MODELS:
        return onboard_routes.pipeline
    if _real_pipeline is None:
        from loip.domains.document_intel.processor import DocumentIntelligenceProcessor
        from loip.pipelines.onboarding import OnboardingPipeline

        logger.info(
            "LOIP_DEMO_REAL_MODELS set — real document intelligence, mocked external clients"
        )
        # Mock everything (keeps CIBIL/UIDAI/NSDL offline), then make only the
        # document-reading stage genuine.
        pipeline = OnboardingPipeline(mock_mode=True)
        pipeline.doc_processor = DocumentIntelligenceProcessor(mock_mode=False)
        _real_pipeline = pipeline
    return _real_pipeline


@router.get("", response_class=HTMLResponse)
async def apply_page(request: Request):
    return templates.TemplateResponse(request=request, name="apply.html", context={})


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
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is not None:
            images.append(img)
            raw_documents.append(contents)
            accepted_documents.append(doc.filename)
        else:
            dropped_documents.append(doc.filename)

    if not images:
        raise HTTPException(status_code=400, detail="No valid document images provided")

    app_data = {
        "application_id": application_id,
        "applicant_name": full_name.strip(),
        "loan_amount": loan_amount,
        "tenure_months": 24,
        "employment_type": employment_type,
        "employment_tier": 3,
        "declared_monthly_income": monthly_income,
    }

    try:
        decision = await _get_pipeline().execute(
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

    decision_payload = decision.model_dump(mode="json")

    record = {
        "application_id": application_id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "form": {
            "full_name": full_name.strip(),
            "mobile_number": mobile_number.strip(),
            "pan_number": pan_number.strip().upper(),
            "aadhaar_number": aadhaar_number.strip(),
            "employment_type": employment_type,
            "monthly_income": monthly_income,
            "loan_amount": loan_amount,
        },
        "real_models": _REAL_MODELS,
        "documents": accepted_documents,
        "dropped_documents": dropped_documents,
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
            "real_models": _REAL_MODELS,
            "stored_at": f"data/demo_applications/{application_id}.json",
        }
    )
