"""Jinja2 template-rendered UI routes for human review."""

import os

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from loip.domains.human_review.schemas import (
    OverrideDecision,
    OverrideReasonCode,
    OverrideRequest,
    ReviewQueueFilters,
)
from loip.web.routes.audit import _explainability_store
from loip.web.routes.review import review_processor

router = APIRouter(prefix="/ui", tags=["UI"])
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
)


@router.get("/queue", response_class=HTMLResponse)
async def queue_page(request: Request):
    cases = review_processor.get_queue(ReviewQueueFilters(sort_by="risk_score", sort_order="desc"))
    summary = review_processor.get_queue_summary()
    return templates.TemplateResponse(
        "queue.html",
        {"request": request, "cases": cases, "summary": summary, "active_page": "queue"},
    )


@router.get("/review/{case_id}", response_class=HTMLResponse)
async def review_detail_page(request: Request, case_id: str):
    case = review_processor.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    decision = case.onboarding_decision
    explainability = _explainability_store.get(case.application_id)

    return templates.TemplateResponse(
        "review_detail.html",
        {
            "request": request,
            "case": case,
            "decision": decision,
            "explainability": explainability,
            "active_page": "review",
        },
    )


@router.post("/review/{case_id}/override")
async def submit_override_form(
    case_id: str,
    override_decision: str = Form(...),
    reason_code: str = Form(...),
    notes: str = Form(...),
    reviewer_id: str = Form(default="reviewer_01"),
):
    case = review_processor.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    request = OverrideRequest(
        reviewer_id=reviewer_id,
        override_decision=OverrideDecision(override_decision),
        reason_code=OverrideReasonCode(reason_code),
        notes=notes,
    )
    review_processor.submit_override(case_id, request)
    return RedirectResponse(url=f"/ui/review/{case_id}", status_code=303)
