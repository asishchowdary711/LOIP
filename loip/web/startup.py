"""Demo data seeding for the review console.

Runs at FastAPI startup (mock mode). Pushes a spread of approve / review /
reject cases into the module-level ``review_processor`` used by the web
routes so the UI has something to show without a database or a separate
seed step. Each case is also run through the real onboarding pipeline, so
the explainability store (SHAP + copilot) is populated too.

This is demo scaffolding, not a production code path — the pipeline runs
in ``mock_mode=True`` and identity extraction returns canned values (see
``loip/evaluate.py``).
"""

from __future__ import annotations

import logging

from loip.evaluate import build_mock_images
from loip.pipelines.onboarding import OnboardingPipeline
from loip.schemas.decision import LoanApplication
from loip.web.routes.review import review_processor

logger = logging.getLogger(__name__)

# Mock PAN/Aadhaar extraction always returns this identity (see loip/evaluate.py).
# Scenarios reuse it for application_data["full_name"] unless deliberately
# creating an identity mismatch. Employer "Acme Corp" matches the mock salary-slip
# extractor, so it avoids an employer_name_mismatch flag on clean cases.
_MOCK_FULL_NAME = "Mock User"
_MOCK_DOB = "01/01/1990"

# (display_name is what the queue/dashboard shows; the underlying extracted
# identity is always "Mock User" in mock mode.)
DEMO_SCENARIOS: list[dict] = [
    {
        "application_id": "APP-1001", "display_name": "Priya Sharma",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 500_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-1002", "display_name": "Rajesh Kumar",
        "segment": "self_employed", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 500_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-1003", "display_name": "Anjali Mehta",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Wrong Corp Pvt Ltd",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 500_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-1004", "display_name": "Vikram Singh",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 800_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-1005", "display_name": "Sneha Patel",
        "segment": "salaried", "employer_tier": 5, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 500_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-1006", "display_name": "Arjun Nair",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 2_000_000, "tenure_months": 12,
    },
    {
        "application_id": "APP-1007", "display_name": "Karan Gupta",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": "Imposter Name", "loan_amount": 500_000, "tenure_months": 36,
    },
]


def _document_store_and_bytes(images):
    """Best-effort MinIO store + PNG-encoded mock-image bytes, so seeded demo
    cases get document-backed evidence chains. Returns (store, raw_bytes) or
    (None, None) if MinIO is unavailable."""
    try:
        import cv2

        from loip.storage import DocumentStore

        store = DocumentStore()
        raw = [cv2.imencode(".png", img)[1].tobytes() for img in images]
        return store, raw
    except Exception as exc:  # noqa: BLE001 - degrade gracefully if MinIO is down
        logger.warning("MinIO unavailable for demo seeding (%s); evidence chains omit document ids", exc)
        return None, None


async def seed_demo_cases() -> int:
    """Seed demo review cases if the queue is empty. Returns count seeded."""
    if review_processor.get_queue():
        logger.info("Review queue already populated; skipping demo seeding")
        return 0

    pipeline = OnboardingPipeline(mock_mode=True)
    images = build_mock_images()
    document_store, raw_documents = _document_store_and_bytes(images)
    seeded = 0

    for sc in DEMO_SCENARIOS:
        application = LoanApplication(
            application_id=sc["application_id"],
            applicant_name=sc["display_name"],
            loan_amount=sc["loan_amount"],
            tenure_months=sc["tenure_months"],
            employment_type=sc["segment"],
            employment_tier=sc["employer_tier"],
            employer_name=sc["employer_name"],
        )
        application_data = application.model_dump(mode="json")
        application_data["full_name"] = sc["full_name"]
        application_data["date_of_birth"] = _MOCK_DOB
        application_data["aadhaar_otp"] = "123456"

        decision = await pipeline.execute(
            application, images, application_data,
            raw_documents=raw_documents,
            document_store=document_store,
        )
        # pipeline.execute stores explainability and creates a case on its OWN
        # ReviewProcessor instance; register it on the web's shared processor too.
        case = review_processor.create_review_case(decision)
        case.applicant_name = sc["display_name"]
        seeded += 1

    logger.info("Seeded %d demo review cases", seeded)
    return seeded
