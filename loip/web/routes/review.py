"""Human review API routes — queue, case detail, override submission."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from loip.domains.human_review.processor import ReviewProcessor
from loip.domains.human_review.schemas import (
    OverrideRecord,
    OverrideRequest,
    ReviewCase,
    ReviewQueueFilters,
    ReviewQueueSummary,
    ReviewStatus,
)

router = APIRouter(prefix="/review", tags=["Human Review"])
review_processor = ReviewProcessor(mock_mode=True)


@router.get("/queue", response_model=list[ReviewCase])
async def get_review_queue(
    status: ReviewStatus | None = None,
    assigned_to: str | None = None,
    min_risk_score: float | None = None,
    sort_by: str = Query(default="risk_score", pattern="^(risk_score|created_at|loan_amount)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    filters = ReviewQueueFilters(
        status=status,
        assigned_to=assigned_to,
        min_risk_score=min_risk_score,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return review_processor.get_queue(filters)


@router.get("/queue/summary", response_model=ReviewQueueSummary)
async def get_queue_summary():
    return review_processor.get_queue_summary()


@router.get("/{case_id}", response_model=ReviewCase)
async def get_review_case(case_id: str):
    case = review_processor.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Review case {case_id} not found")
    return case


class AssignRequest(BaseModel):
    reviewer_id: str


@router.post("/{case_id}/assign", response_model=ReviewCase)
async def assign_case(case_id: str, request: AssignRequest):
    case = review_processor.assign_case(case_id, request.reviewer_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Review case {case_id} not found")
    return case


@router.post("/{case_id}/override", response_model=OverrideRecord)
async def submit_override(case_id: str, request: OverrideRequest):
    case = review_processor.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Review case {case_id} not found")
    if case.status == ReviewStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Case already completed")

    override = review_processor.submit_override(case_id, request)
    if override is None:
        raise HTTPException(status_code=500, detail="Failed to submit override")
    return override


@router.get("/{case_id}/overrides", response_model=list[OverrideRecord])
async def get_case_overrides(case_id: str):
    case = review_processor.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Review case {case_id} not found")
    return review_processor.get_overrides(case.application_id)
