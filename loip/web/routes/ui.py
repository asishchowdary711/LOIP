"""Jinja2 template-rendered UI routes for the review console."""

import logging
import os

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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


# Per user request: /ui and /ui/queue serve the Claude-generated standalone
# Review Console (a self-contained React bundle with hard-coded sample data).
# No live data wiring on these two pages; the live case-detail page at
# /ui/review/{case_id} still renders against review_processor.
_STANDALONE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "LOIP Review Console (standalone).html",
)


@router.get("", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    # no-store keeps the browser from holding an old copy of the standalone
    # while we iterate on the HTML; otherwise edits look "not applied" until
    # a hard reload.
    return FileResponse(
        _STANDALONE_PATH,
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/queue")
async def queue_page(request: Request):
    # The standalone is a hash-routed SPA — point /ui/queue at the same file
    # with #queue so the in-page router lands on the Queue screen.
    return RedirectResponse(url="/ui#queue", status_code=307)


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
