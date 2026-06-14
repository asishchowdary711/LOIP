"""Evidence/traceability API routes — evidence chains and source-location lookups."""

from fastapi import APIRouter, Depends, HTTPException

from loip.web.auth import AuthenticatedUser, require_permission

router = APIRouter(prefix="/evidence", tags=["Evidence"])


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
