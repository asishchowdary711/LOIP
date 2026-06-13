"""Audit view API routes — evidence chains, SHAP explanations, copilot narratives."""

from fastapi import APIRouter, HTTPException

from loip.domains.explainability.schemas import ExplainabilityResult
from loip.domains.human_review.processor import ReviewProcessor

router = APIRouter(prefix="/audit", tags=["Audit"])

_explainability_store: dict[str, ExplainabilityResult] = {}


def store_explainability(application_id: str, result: ExplainabilityResult) -> None:
    _explainability_store[application_id] = result


@router.get("/{application_id}/explainability", response_model=ExplainabilityResult)
async def get_explainability(application_id: str):
    result = _explainability_store.get(application_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Explainability data not found for {application_id}")
    return result


@router.get("/{application_id}/evidence-chains")
async def get_evidence_chains(application_id: str):
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


@router.get("/{application_id}/retraining-data")
async def get_retraining_data(application_id: str | None = None):
    from loip.web.routes.review import review_processor
    return {"data": review_processor.get_retraining_data()}
