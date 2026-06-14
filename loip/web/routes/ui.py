"""Jinja2 template-rendered UI routes for the review console."""

import logging
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
from loip.schemas.decision import Decision
from loip.web.routes.audit import _explainability_store
from loip.web.routes.review import review_processor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ui", tags=["UI"])
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
)


def _inr(value: float | int | None) -> str:
    """Format a number with thousands separators (Jinja's `format` filter is
    %-style and can't do `{:,.0f}`)."""
    if value is None:
        return "-"
    return f"{value:,.0f}"


templates.env.filters["inr"] = _inr


def _collect_evidence_chains(decision) -> list:
    """Flatten evidence chains from the decision and all sub-results."""
    if decision is None:
        return []
    chains = list(decision.evidence_chains)
    for result in (
        decision.identity_result,
        decision.income_result,
        decision.affordability_result,
    ):
        if result is not None:
            chains.extend(result.evidence_chains)
    return chains


@router.get("", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    cases = review_processor.get_queue(
        ReviewQueueFilters(sort_by="risk_score", sort_order="desc", page_size=100)
    )
    summary = review_processor.get_queue_summary()

    by_decision = {Decision.APPROVE: 0, Decision.REVIEW: 0, Decision.REJECT: 0}
    foirs, cibils, risks = [], [], []
    for case in cases:
        by_decision[case.system_decision] = by_decision.get(case.system_decision, 0) + 1
        if case.foir is not None:
            foirs.append(case.foir)
        if case.cibil_score is not None:
            cibils.append(case.cibil_score)
        if case.risk_score is not None:
            risks.append(case.risk_score)

    stats = {
        "total": len(cases),
        "approve": by_decision.get(Decision.APPROVE, 0),
        "review": by_decision.get(Decision.REVIEW, 0),
        "reject": by_decision.get(Decision.REJECT, 0),
        "avg_foir": (sum(foirs) / len(foirs)) if foirs else 0.0,
        "avg_cibil": (sum(cibils) / len(cibils)) if cibils else 0.0,
        "avg_risk": (sum(risks) / len(risks)) if risks else 0.0,
    }
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"stats": stats, "summary": summary, "cases": cases, "active_page": "dashboard"},
    )


@router.get("/queue", response_class=HTMLResponse)
async def queue_page(request: Request):
    cases = review_processor.get_queue(ReviewQueueFilters(sort_by="risk_score", sort_order="desc"))
    summary = review_processor.get_queue_summary()
    return templates.TemplateResponse(
        request=request,
        name="queue.html",
        context={"request": request, "cases": cases, "summary": summary, "active_page": "queue"},
    )


@router.get("/review/{case_id}", response_class=HTMLResponse)
async def review_detail_page(request: Request, case_id: str):
    case = review_processor.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    decision = case.onboarding_decision
    explainability = _explainability_store.get(case.application_id)
    evidence_chains = _collect_evidence_chains(decision)

    return templates.TemplateResponse(
        request=request,
        name="review_detail.html",
        context={
            "request": request,
            "case": case,
            "decision": decision,
            "explainability": explainability,
            "evidence_chains": evidence_chains,
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
    original_decision = case.system_decision.value
    review_processor.submit_override(case_id, request)

    # Persist best-effort so the override and new status survive restarts.
    try:
        from loip import persistence

        await persistence.save_override(
            case.application_id,
            reviewer_id=reviewer_id,
            original_decision=original_decision,
            override_decision=request.override_decision.value,
            reason_code=request.reason_code.value,
            notes=request.notes,
            review_status=case.status.value,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not persist override for %s: %s", case.application_id, exc)

    return RedirectResponse(url=f"/ui/review/{case_id}", status_code=303)
