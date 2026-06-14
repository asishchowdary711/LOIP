"""Capture full-page screenshots of the LOIP review console UI.

Assumes the API is running locally (see docs/RUNBOOK.md). Saves PNGs to
``loip/docs/screenshots/``. Run with the project venv:

    PYTHONPATH=/workspaces/LOIP loip/.venv/bin/python -m scripts.capture_screenshots
"""

from __future__ import annotations

import sys

import httpx
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
OUT_DIR = "/workspaces/LOIP/loip/docs/screenshots"


def _pick_case(decision: str) -> dict:
    cases = httpx.get(f"{BASE}/review/queue", timeout=15).json()
    for c in cases:
        if c["system_decision"] == decision:
            return c
    return cases[0]


def main() -> int:
    review_case = _pick_case("review")
    reject_case = _pick_case("reject")

    # (filename, url, css selector to wait for before shooting)
    shots = [
        ("01_dashboard.png", f"{BASE}/ui", "table"),
        ("02_review_queue.png", f"{BASE}/ui/queue", "table"),
        ("03_review_detail.png", f"{BASE}/ui/review/{review_case['case_id']}", ".card"),
        ("04_review_detail_reject.png", f"{BASE}/ui/review/{reject_case['case_id']}", ".card"),
        ("05_api_docs.png", f"{BASE}/docs", ".opblock"),  # Swagger renders async
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        for name, url, selector in shots:
            page.goto(url, wait_until="networkidle")
            page.wait_for_selector(selector, timeout=15000)
            page.wait_for_timeout(800)
            path = f"{OUT_DIR}/{name}"
            page.screenshot(path=path, full_page=True)
            print(f"  saved {path}  <- {url}")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
