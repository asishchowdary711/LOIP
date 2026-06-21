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

# Document store: MinIO if reachable, otherwise a local filesystem fallback
# that mirrors the same id format ("<bucket>/<uuid>.<ext>"). The fallback
# keeps evidence chains populated (with resolvable document_ids) even when
# MinIO isn't running, so traceability never silently degrades to empty.
try:
    from loip.storage import DocumentStore, LocalDocumentStore, open_document_store

    document_store = open_document_store()
    if isinstance(document_store, LocalDocumentStore):
        logger.info(
            "MinIO unreachable; using local document store at %s — evidence chains stay populated",
            document_store.root,
        )
    else:
        logger.info("MinIO document store connected; uploaded documents will be persisted")
except Exception as exc:  # noqa: BLE001 - last-resort guard
    document_store = None
    logger.warning("Document store unavailable (%s); documents will not be persisted", exc)

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
