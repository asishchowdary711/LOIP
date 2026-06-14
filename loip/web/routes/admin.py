"""Admin API routes — model registry, drift monitoring, retraining, API key inventory."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from loip.domains.mlops.processor import MLOpsProcessor
from loip.domains.mlops.schemas import ModelStage
from loip.web.auth import _API_KEYS, AuthenticatedUser, require_permission

router = APIRouter(prefix="/admin", tags=["Admin"])
mlops = MLOpsProcessor(mock_mode=True)


class PromotionRequest(BaseModel):
    version: str
    to_stage: ModelStage


@router.get("/models")
async def list_models(
    user: AuthenticatedUser = Depends(require_permission("admin:read")),
):
    return {"models": [m.model_dump() for m in mlops.get_production_models()]}


@router.post("/models/{model_name}/promote")
async def promote_model(
    model_name: str,
    body: PromotionRequest,
    user: AuthenticatedUser = Depends(require_permission("admin:write")),
):
    gate = mlops.promote_model(model_name, body.version, body.to_stage)
    if gate is None:
        raise HTTPException(status_code=404, detail=f"Model {model_name}:{body.version} not found")
    return gate.model_dump()


@router.get("/drift-alerts")
async def list_drift_alerts(
    acknowledged: bool | None = None,
    user: AuthenticatedUser = Depends(require_permission("admin:read")),
):
    return {"alerts": [a.model_dump() for a in mlops.get_drift_alerts(acknowledged)]}


@router.post("/drift-alerts/{alert_id}/acknowledge")
async def acknowledge_drift_alert(
    alert_id: str,
    user: AuthenticatedUser = Depends(require_permission("admin:write")),
):
    acknowledged = mlops.acknowledge_alert(alert_id)
    if not acknowledged:
        raise HTTPException(status_code=404, detail=f"Drift alert {alert_id} not found")
    return {"alert_id": alert_id, "acknowledged": True}


@router.get("/retraining-triggers")
async def list_retraining_triggers(
    user: AuthenticatedUser = Depends(require_permission("admin:read")),
):
    return {"triggers": [t.model_dump() for t in mlops.get_retraining_triggers()]}


@router.post("/retraining/{model_name}/trigger")
async def trigger_retraining(
    model_name: str,
    user: AuthenticatedUser = Depends(require_permission("admin:write")),
):
    trigger = mlops.trigger_scheduled_retraining(model_name)
    return trigger.model_dump()


@router.get("/feature-views")
async def list_feature_views(
    user: AuthenticatedUser = Depends(require_permission("admin:read")),
):
    return {"feature_views": [f.model_dump() for f in mlops.get_feature_views()]}


@router.get("/api-keys")
async def list_api_keys(
    user: AuthenticatedUser = Depends(require_permission("admin:read")),
):
    return {
        "api_keys": [
            {"user_id": data["user_id"], "role": data["role"]}
            for data in _API_KEYS.values()
        ]
    }
