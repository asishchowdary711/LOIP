"""MLOps processor — model registry, feature store, drift monitoring, retraining orchestration."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from loip.domains.mlops.schemas import (
    DriftAlert,
    DriftSeverity,
    DriftType,
    FeatureView,
    ModelStage,
    PromotionGate,
    RegisteredModel,
    RetrainingTrigger,
)

logger = logging.getLogger(__name__)

FEATURE_VIEWS = [
    FeatureView(name="identity_features", domain="identity", features=[
        "identity_confidence", "pan_verified", "aadhaar_verified",
        "face_match_score", "liveness_score", "tamper_flag_count",
    ]),
    FeatureView(name="income_features", domain="income", features=[
        "verified_monthly_income", "income_confidence", "salary_credit_cv",
        "income_source_count", "anomaly_flag_count",
    ]),
    FeatureView(name="affordability_features", domain="affordability", features=[
        "foir", "dti", "disposable_income", "liquidity_score",
        "cashflow_stability", "financial_stress_score",
    ]),
    FeatureView(name="fraud_features", domain="fraud", features=[
        "fraud_score", "graph_fraud_score", "behavioral_anomaly_score",
        "signal_count", "forgery_flag_count",
    ]),
    FeatureView(name="risk_features", domain="risk", features=[
        "risk_score", "cibil_score_normalized", "employment_tier",
        "loan_to_income_ratio", "ensemble_confidence",
    ]),
]

PROMOTION_GATES: dict[str, dict[str, float]] = {
    "risk_xgboost": {"auc_roc": 0.85, "f1_score": 0.80},
    "income_xgboost": {"mae": 5000.0, "r2_score": 0.85},
    "affordability_lightgbm": {"auc_roc": 0.82, "f1_score": 0.78},
}

DRIFT_THRESHOLDS: dict[str, float] = {
    "data_drift": 0.15,
    "model_drift": 0.10,
    "target_drift": 0.20,
}


class MLOpsProcessor:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self._models: dict[str, RegisteredModel] = {}
        self._drift_alerts: list[DriftAlert] = []
        self._retraining_triggers: list[RetrainingTrigger] = []

    def register_model(
        self,
        model_name: str,
        version: str,
        metrics: dict[str, float],
        run_id: str | None = None,
    ) -> RegisteredModel:
        model = RegisteredModel(
            model_name=model_name,
            version=version,
            stage=ModelStage.DEVELOPMENT,
            run_id=run_id or str(uuid.uuid4()),
            metrics=metrics,
        )
        key = f"{model_name}:{version}"
        self._models[key] = model
        logger.info("Registered model %s v%s", model_name, version)
        return model

    def promote_model(self, model_name: str, version: str, to_stage: ModelStage) -> PromotionGate | None:
        key = f"{model_name}:{version}"
        model = self._models.get(key)
        if model is None:
            return None

        gates = PROMOTION_GATES.get(model_name, {})
        for metric_name, threshold in gates.items():
            actual = model.metrics.get(metric_name, 0.0)
            is_lower_better = metric_name in ("mae", "mse", "rmse")
            passed = actual <= threshold if is_lower_better else actual >= threshold

            if not passed:
                gate = PromotionGate(
                    model_name=model_name,
                    from_stage=model.stage,
                    to_stage=to_stage,
                    required_metric=metric_name,
                    threshold=threshold,
                    actual_value=actual,
                    passed=False,
                )
                logger.warning("Promotion gate failed: %s %s=%s < %s", model_name, metric_name, actual, threshold)
                return gate

        model.stage = to_stage
        model.promoted_at = datetime.now(UTC)

        return PromotionGate(
            model_name=model_name,
            from_stage=ModelStage.DEVELOPMENT,
            to_stage=to_stage,
            required_metric=list(gates.keys())[0] if gates else "none",
            threshold=list(gates.values())[0] if gates else 0.0,
            actual_value=model.metrics.get(list(gates.keys())[0], 0.0) if gates else 0.0,
            passed=True,
        )

    def get_feature_views(self) -> list[FeatureView]:
        return FEATURE_VIEWS

    def check_drift(
        self,
        model_name: str,
        drift_type: DriftType,
        drift_score: float,
        feature_name: str | None = None,
    ) -> DriftAlert | None:
        threshold = DRIFT_THRESHOLDS.get(drift_type.value, 0.15)
        if drift_score < threshold:
            return None

        if drift_score >= threshold * 2:
            severity = DriftSeverity.CRITICAL
        elif drift_score >= threshold * 1.5:
            severity = DriftSeverity.HIGH
        elif drift_score >= threshold * 1.2:
            severity = DriftSeverity.MEDIUM
        else:
            severity = DriftSeverity.LOW

        alert = DriftAlert(
            alert_id=str(uuid.uuid4()),
            model_name=model_name,
            drift_type=drift_type,
            severity=severity,
            feature_name=feature_name,
            drift_score=drift_score,
            threshold=threshold,
            details=f"{drift_type.value} detected on {model_name}: score={drift_score:.3f} (threshold={threshold})",
        )
        self._drift_alerts.append(alert)
        logger.warning("Drift alert: %s", alert.details)

        if severity in (DriftSeverity.HIGH, DriftSeverity.CRITICAL):
            self._trigger_retraining(model_name, "drift_alert", alert.alert_id)

        return alert

    def _trigger_retraining(
        self,
        model_name: str,
        reason: str,
        drift_alert_id: str | None = None,
        override_count: int = 0,
    ) -> RetrainingTrigger:
        trigger = RetrainingTrigger(
            trigger_id=str(uuid.uuid4()),
            reason=reason,
            model_name=model_name,
            drift_alert_id=drift_alert_id,
            override_count=override_count,
        )
        self._retraining_triggers.append(trigger)
        logger.info("Retraining triggered for %s: reason=%s", model_name, reason)
        return trigger

    def trigger_scheduled_retraining(self, model_name: str) -> RetrainingTrigger:
        return self._trigger_retraining(model_name, "scheduled_weekly")

    def trigger_override_retraining(self, model_name: str, override_count: int) -> RetrainingTrigger:
        return self._trigger_retraining(model_name, "override_feedback", override_count=override_count)

    def get_drift_alerts(self, acknowledged: bool | None = None) -> list[DriftAlert]:
        if acknowledged is None:
            return list(self._drift_alerts)
        return [a for a in self._drift_alerts if a.acknowledged == acknowledged]

    def acknowledge_alert(self, alert_id: str) -> bool:
        for alert in self._drift_alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                return True
        return False

    def get_retraining_triggers(self) -> list[RetrainingTrigger]:
        return list(self._retraining_triggers)

    def get_production_models(self) -> list[RegisteredModel]:
        return [m for m in self._models.values() if m.stage == ModelStage.PRODUCTION]
