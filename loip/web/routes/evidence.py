"""Evidence/traceability API routes — evidence chains and source-location lookups."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from loip.web.auth import AuthenticatedUser, require_permission

router = APIRouter(prefix="/evidence", tags=["Evidence"])


_CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "pdf": "application/pdf",
}


@router.get("/{application_id}/chains")
async def get_evidence_chains(
    application_id: str,
    user: AuthenticatedUser = Depends(require_permission("audit:read")),
):
    from loip.web.routes.review import review_processor

    case = review_processor.get_case_by_application(application_id)
    if case is None or case.onboarding_decision is None:
        raise HTTPException(status_code=404, detail=f"No decision data for application {application_id}")

    decision = case.onboarding_decision
    chains = []
    chains.extend([c.model_dump() for c in decision.evidence_chains])
    if decision.identity_result:
        chains.extend([c.model_dump() for c in decision.identity_result.evidence_chains])
    if decision.income_result:
        chains.extend([c.model_dump() for c in decision.income_result.evidence_chains])
    if decision.affordability_result:
        chains.extend([c.model_dump() for c in decision.affordability_result.evidence_chains])

    return {"application_id": application_id, "evidence_chains": chains}


@router.get("/{application_id}/source/{field_name}")
async def get_field_source(
    application_id: str,
    field_name: str,
    user: AuthenticatedUser = Depends(require_permission("audit:read")),
):
    from loip.web.routes.review import review_processor

    case = review_processor.get_case_by_application(application_id)
    if case is None or case.onboarding_decision is None:
        raise HTTPException(status_code=404, detail=f"No decision data for application {application_id}")

    decision = case.onboarding_decision
    chains = list(decision.evidence_chains)
    if decision.identity_result:
        chains.extend(decision.identity_result.evidence_chains)
    if decision.income_result:
        chains.extend(decision.income_result.evidence_chains)
    if decision.affordability_result:
        chains.extend(decision.affordability_result.evidence_chains)

    for chain in chains:
        for field in [*chain.supporting, *chain.contradicting]:
            if field.field_name == field_name:
                return {
                    "application_id": application_id,
                    "field_name": field_name,
                    "source": field.source.model_dump(),
                    "raw_value": field.raw_value,
                    "normalized_value": field.normalized_value,
                    "confidence": field.confidence,
                }

    raise HTTPException(
        status_code=404,
        detail=f"No source location found for field '{field_name}' on application {application_id}",
    )


@router.get("/document/{document_id:path}")
async def get_document(
    document_id: str,
    user: AuthenticatedUser = Depends(require_permission("audit:read")),
):
    """Stream the raw bytes of a stored source document so a reviewer can
    click an evidence chain back to the actual PDF/image that produced the
    field. Works against either the MinIO store or the local filesystem
    fallback — both expose ``"<bucket>/<uuid>.<ext>"`` ids."""
    from loip.web.routes.onboard import document_store

    if document_store is None:
        raise HTTPException(status_code=503, detail="Document store not initialised")

    # Reject anything that doesn't look like "<bucket>/<filename>" before we
    # touch the backend — the local store already blocks path traversal, but
    # we want a tight 400 here rather than a 404 from a malformed id.
    bucket, _, object_name = document_id.partition("/")
    if not bucket or not object_name or "/" in object_name or ".." in object_name:
        raise HTTPException(status_code=400, detail="Invalid document_id")

    if not document_store.exists(document_id):
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

    try:
        data = document_store.get(document_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to read document: {exc}")

    ext = object_name.rsplit(".", 1)[-1].lower() if "." in object_name else ""
    return Response(content=data, media_type=_CONTENT_TYPES.get(ext, "application/octet-stream"))
