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

from loip import persistence
from loip.domains.human_review.schemas import ReviewStatus
from loip.evaluate import build_mock_images
from loip.pipelines.onboarding import OnboardingPipeline
from loip.schemas.decision import LoanApplication
from loip.web.routes.audit import _explainability_store, store_explainability
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
# Scenarios sourced from annotation_sample25 — 20 real test personas covering
# all three decision outcomes. Employer "Acme Corp" matches the mock salary-slip
# extractor; "Wrong Corp Pvt Ltd" triggers employer_name_mismatch → REVIEW;
# full_name "Imposter Name" triggers identity_mismatch → REJECT.
DEMO_SCENARIOS: list[dict] = [
    # --- APPROVE: clean docs, tier 1-3, loan ≤ 2L (below V-CIP threshold), FOIR well under 0.50 ---
    {
        "application_id": "APP-AS-001", "display_name": "Leena Vasa",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 150_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-AS-002", "display_name": "Sneha Gola",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 150_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-AS-003", "display_name": "Amol Parekh",
        "segment": "salaried", "employer_tier": 3, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 150_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-AS-004", "display_name": "Kabir Setty",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 150_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-AS-005", "display_name": "Luke Ahluwalia",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 150_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-AS-006", "display_name": "Anamika Bath",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 150_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-AS-007", "display_name": "Charles Sodhi",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 150_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-AS-008", "display_name": "Dakshesh Madan",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 150_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-AS-009", "display_name": "Azad Walla",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 150_000, "tenure_months": 36,
    },
    # --- REVIEW: soft flags (employer mismatch / high tier / marginal FOIR) ---
    {
        "application_id": "APP-AS-010", "display_name": "George Vala",
        "segment": "salaried", "employer_tier": 4, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 500_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-AS-011", "display_name": "Aayush Deshmukh",
        "segment": "salaried", "employer_tier": 5, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 500_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-AS-012", "display_name": "Ishanvi Vyas",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Wrong Corp Pvt Ltd",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 500_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-AS-013", "display_name": "Shivansh Cherian",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Wrong Corp Pvt Ltd",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 500_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-AS-014", "display_name": "Yatan Borra",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 800_000, "tenure_months": 36,
    },
    # --- REJECT: hard failures (FOIR exceeded / identity mismatch / synthetic identity) ---
    {
        "application_id": "APP-AS-015", "display_name": "Meera Dey",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": _MOCK_FULL_NAME, "loan_amount": 2_000_000, "tenure_months": 12,
    },
    {
        "application_id": "APP-AS-016", "display_name": "Saksham Mane",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": "Imposter Name", "loan_amount": 500_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-AS-017", "display_name": "Mitali Dash",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": "Imposter Name", "loan_amount": 500_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-AS-018", "display_name": "Nayar Isaac",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": "Imposter Name", "loan_amount": 500_000, "tenure_months": 36,
    },
    {
        "application_id": "APP-AS-019", "display_name": "Falak Sankaran",
        "segment": "salaried", "employer_tier": 2, "employer_name": "Acme Corp",
        "full_name": "Imposter Name", "loan_amount": 2_000_000, "tenure_months": 12,
    },
    {
        "application_id": "APP-AS-020", "display_name": "Champak Hegde",
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


async def seed_demo_cases(event_publisher=None, identity_graph=None) -> int:
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
            event_publisher=event_publisher,
            identity_graph=identity_graph,
        )
        # pipeline.execute stores explainability and creates a case on its OWN
        # ReviewProcessor instance; register it on the web's shared processor too.
        case = review_processor.create_review_case(decision)
        case.applicant_name = sc["display_name"]

        # Persist best-effort so the queue survives restarts.
        try:
            await persistence.save_decision(
                decision,
                applicant_name=sc["display_name"],
                explainability=_explainability_store.get(decision.application_id),
                review_status=ReviewStatus.PENDING.value,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not persist seeded case %s: %s", sc["application_id"], exc)

        seeded += 1

    logger.info("Seeded %d demo review cases", seeded)
    return seeded


def _to_review_status(value: str | None) -> ReviewStatus:
    try:
        return ReviewStatus(value)
    except (ValueError, TypeError):
        return ReviewStatus.PENDING


async def _rehydrate_from_db() -> int:
    """Rebuild the in-memory review queue from persisted decisions. Returns the
    number of cases restored (0 if the DB is empty or unreachable)."""
    rows = await persistence.load_decisions()
    for row in rows:
        decision = row["decision"]
        case = review_processor.create_review_case(decision)
        case.applicant_name = row["applicant_name"]
        case.status = _to_review_status(row["status"])
        if row["explainability"] is not None:
            store_explainability(decision.application_id, row["explainability"])
    return len(rows)


async def bootstrap_review_console(event_publisher=None, identity_graph=None) -> int:
    """Rehydrate the review queue from Postgres; if empty, seed demo cases.

    Falls back to in-memory-only demo seeding if Postgres is unreachable, so
    the console still works without the Docker stack.
    """
    try:
        await persistence.init_models()
        restored = await _rehydrate_from_db()
        if restored:
            logger.info("Rehydrated %d review cases from Postgres", restored)
            return restored
    except Exception as exc:  # noqa: BLE001
        logger.warning("Postgres unavailable (%s); seeding in-memory demo data only", exc)

    return await seed_demo_cases(event_publisher=event_publisher, identity_graph=identity_graph)
