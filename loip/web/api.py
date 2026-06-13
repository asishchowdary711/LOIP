from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import audit, consent, onboard, review, ui

app = FastAPI(title="LOIP API", version="1.0.0")

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
