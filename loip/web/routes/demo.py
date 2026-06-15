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

# The four documents the demo collects, in submission order.
DEMO_DOCUMENT_SLOTS = ["aadhaar", "pan", "salary_slip", "bank_statement"]


def _storage_dir() -> str:
    os.makedirs(_DATA_DIR, exist_ok=True)
    return _DATA_DIR


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
    for doc in documents:
        contents = await doc.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is not None:
            images.append(img)
            raw_documents.append(contents)

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
        decision = await onboard_routes.pipeline.execute(
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
        "documents": [doc.filename for doc in documents],
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
            "stored_at": f"data/demo_applications/{application_id}.json",
        }
    )
