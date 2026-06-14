import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .auth import limiter
from .routes import admin, audit, consent, evidence, onboard, review, ui

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from loip.events import EventPublisher

    from .startup import bootstrap_review_console

    # Shared Kafka publisher (best-effort; no-ops if the broker is down).
    publisher = EventPublisher()
    await publisher.start()
    app.state.event_publisher = publisher
    from .routes import onboard as onboard_routes
    onboard_routes.event_publisher = publisher

    try:
        await bootstrap_review_console(event_publisher=publisher)
    except Exception:
        logger.exception("Review console bootstrap failed; it will start empty")

    yield

    await publisher.stop()


app = FastAPI(title="LOIP API", version="1.0.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(onboard.router)
app.include_router(review.router)
app.include_router(audit.router)
app.include_router(evidence.router)
app.include_router(admin.router)
app.include_router(ui.router)
app.include_router(consent.router)


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/health/ready")
async def readiness_check():
    from loip import persistence

    postgres_ok = await persistence.healthcheck()

    minio_ok = False
    try:
        from loip.storage import DocumentStore

        minio_ok = DocumentStore(ensure_buckets=False).client.bucket_exists("evidence")
    except Exception:  # noqa: BLE001
        minio_ok = False

    kafka_ok = getattr(getattr(app.state, "event_publisher", None), "ready", False)

    # Wired and health-checked today: Postgres + MinIO + Kafka. The rest are
    # defined in docker-compose.yml but not yet in the request path (None).
    deps = {
        "postgresql": postgres_ok,
        "minio": minio_ok,
        "kafka": kafka_ok,
        "redis": None,
        "opensearch": None,
        "neo4j": None,
    }
    wired_ok = postgres_ok and minio_ok
    return {"status": "ready" if wired_ok else "degraded", "dependencies": deps}


@app.get("/health/live")
def liveness_check():
    return {"status": "alive"}
