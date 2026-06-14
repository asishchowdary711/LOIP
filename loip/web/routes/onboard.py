import json
import logging

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from loip.pipelines.onboarding import OnboardingPipeline
from loip.schemas.decision import LoanApplication, OnboardingDecision
from loip.web.auth import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboard", tags=["Onboarding"])
pipeline = OnboardingPipeline(mock_mode=True)

# Best-effort MinIO document store. If MinIO is unreachable (e.g. Docker not
# running), fall back to None — the pipeline then skips document persistence
# and evidence chains simply omit document-backed source locations.
try:
    from loip.storage import DocumentStore

    document_store = DocumentStore()
    logger.info("MinIO document store connected; uploaded documents will be persisted")
except Exception as exc:  # noqa: BLE001 - degrade gracefully if MinIO is down
    document_store = None
    logger.warning("MinIO document store unavailable (%s); documents will not be persisted", exc)

# Set by the app lifespan (loip/web/api.py) once the Kafka producer + Neo4j
# identity graph are started.
event_publisher = None
identity_graph = None


@router.post("", response_model=OnboardingDecision)
@limiter.limit("10/minute")
async def onboard_application(
    request: Request,
    application: str = Form(...),
    documents: list[UploadFile] = File(...),
):
    try:
        app_data = json.loads(application)
        loan_app = LoanApplication(**app_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid application data: {str(e)}")

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
        raise HTTPException(status_code=400, detail="No valid images provided")

    try:
        decision = await pipeline.execute(
            loan_app, images, app_data,
            raw_documents=raw_documents,
            document_store=document_store,
            event_publisher=event_publisher,
            identity_graph=identity_graph,
        )
        return decision
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")
