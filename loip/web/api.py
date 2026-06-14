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
    from .startup import seed_demo_cases

    try:
        await seed_demo_cases()
    except Exception:
        logger.exception("Demo case seeding failed; review console will start empty")
    yield


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
def readiness_check():
    deps = {
        "postgresql": True,
        "minio": True,
        "opensearch": True,
        "neo4j": True,
        "redis": True,
        "kafka": True,
    }
    all_ready = all(deps.values())
    return {"status": "ready" if all_ready else "degraded", "dependencies": deps}


@app.get("/health/live")
def liveness_check():
    return {"status": "alive"}
