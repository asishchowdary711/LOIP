"""Root landing page — the single entry point for the demo.

One URL (``/``) presents the two actors in the workflow: the customer
(apply for a loan) and the bank admin (review console). A "track application"
box jumps to the customer status page by application id.
"""

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["Home"])

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    return templates.TemplateResponse(request=request, name="landing.html", context={})
