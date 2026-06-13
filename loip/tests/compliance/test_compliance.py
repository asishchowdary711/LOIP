"""Phase 4 tests — DPDP consent, PII masking, PMLA/AML, RBI DLG, RBAC, MLOps."""

import pytest

from loip.domains.compliance.processor import ComplianceProcessor
from loip.domains.compliance.schemas import (
    AMLRiskLevel,
    CancellationStatus,
    KFSStatus,
    PEPStatus,
)
from loip.domains.mlops.processor import MLOpsProcessor
from loip.domains.mlops.schemas import DriftType, ModelStage
from loip.schemas.consent import ConsentPurpose, ConsentStatus
from loip.web.auth import AuthenticatedUser, Role


class TestDPDPConsent:
    def test_record_and_verify_consent(self):
        proc = ComplianceProcessor(mock_mode=True)
        proc.record_consent(
            application_id="APP-001",
            data_principal_id="DP-001",
            purpose=ConsentPurpose.CREDIT_BUREAU_PULL,
            consent_version="1.0",
            document_hash="abc123",
        )
        assert proc.verify_consent("APP-001", ConsentPurpose.CREDIT_BUREAU_PULL)

    def test_missing_consent_returns_false(self):
        proc = ComplianceProcessor(mock_mode=True)
        assert not proc.verify_consent("APP-NONE", ConsentPurpose.CREDIT_BUREAU_PULL)

    def test_consent_withdrawal_blocks_verification(self):
        proc = ComplianceProcessor(mock_mode=True)
        proc.record_consent("APP-002", "DP-002", ConsentPurpose.KYC_VERIFICATION, "1.0", "hash1")
        assert proc.verify_consent("APP-002", ConsentPurpose.KYC_VERIFICATION)

        proc.withdraw_consent("APP-002", ConsentPurpose.KYC_VERIFICATION)
        assert not proc.verify_consent("APP-002", ConsentPurpose.KYC_VERIFICATION)

    def test_withdrawal_records_timestamp(self):
        proc = ComplianceProcessor(mock_mode=True)
        proc.record_consent("APP-003", "DP-003", ConsentPurpose.DATA_STORAGE, "1.0", "hash2")
        proc.withdraw_consent("APP-003", ConsentPurpose.DATA_STORAGE)

        records = proc.get_consent_records("APP-003")
        assert records[0].status == ConsentStatus.WITHDRAWN
        assert records[0].withdrawn_at is not None

    def test_consent_required_before_bureau_pull(self):
        proc = ComplianceProcessor(mock_mode=True)
        assert not proc.verify_consent("APP-NO-CONSENT", ConsentPurpose.CREDIT_BUREAU_PULL)


class TestDataDeletion:
    def test_delete_personal_data_returns_tombstone(self):
        proc = ComplianceProcessor(mock_mode=True)
        result = proc.delete_personal_data("APP-DEL-001", "DP-DEL-001")

        assert result.application_id == "APP-DEL-001"
        assert result.audit_tombstone_id is not None
        assert "applicant_name" in result.fields_deleted
        assert "pan_number" in result.fields_deleted
        assert "aadhaar_number" in result.fields_deleted
        assert len(result.documents_deleted) > 0
        assert result.completed_at is not None

    def test_data_summary_lists_categories(self):
        proc = ComplianceProcessor(mock_mode=True)
        summary = proc.get_data_summary("APP-SUM-001")

        assert summary["application_id"] == "APP-SUM-001"
        assert "identity_documents" in summary["data_categories_held"]
        assert "retention_policy" in summary


class TestPIIMasking:
    def test_mask_pan(self):
        assert ComplianceProcessor.mask_pan("ABCDE1234F") == "ABCDE***F"

    def test_mask_aadhaar(self):
        assert ComplianceProcessor.mask_aadhaar("123456789012") == "**** **** 9012"

    def test_mask_phone(self):
        assert ComplianceProcessor.mask_phone("+91-9876543210") == "******3210"

    def test_mask_email(self):
        assert ComplianceProcessor.mask_email("rajesh@example.com") == "r***@example.com"

    def test_mask_pii_in_text(self):
        proc = ComplianceProcessor(mock_mode=True)
        text = "PAN: ABCDE1234F, Aadhaar: 1234 5678 9012, Phone: 9876543210"
        masked, result = proc.mask_pii_in_text(text)

        assert "ABCDE1234F" not in masked
        assert "1234 5678 9012" not in masked
        assert "9876543210" not in masked
        assert result.masked_field_count > 0
        assert "PAN" in result.entities_detected


class TestPMLAAML:
    def test_pep_screening_returns_clear(self):
        proc = ComplianceProcessor(mock_mode=True)
        result = proc.screen_pep("APP-PEP-001", "Test User", "ABCDE1234F")

        assert result.status == PEPStatus.CLEAR

    def test_high_value_loan_triggers_enhanced_dd(self):
        proc = ComplianceProcessor(mock_mode=True)
        result = proc.check_aml("APP-AML-001", loan_amount=6_000_000)

        assert result.is_high_value
        assert result.requires_enhanced_dd
        assert result.requires_senior_reviewer
        assert result.risk_level == AMLRiskLevel.ENHANCED

    def test_standard_loan_no_enhanced_dd(self):
        proc = ComplianceProcessor(mock_mode=True)
        result = proc.check_aml("APP-AML-002", loan_amount=500_000)

        assert not result.is_high_value
        assert not result.requires_enhanced_dd
        assert result.risk_level == AMLRiskLevel.STANDARD

    def test_high_fraud_score_flags_sar(self):
        proc = ComplianceProcessor(mock_mode=True)
        result = proc.check_aml("APP-AML-003", loan_amount=300_000, fraud_score=0.90)

        assert result.sar_flagged


class TestRBIDLG:
    def test_kfs_generation_computes_emi(self):
        proc = ComplianceProcessor(mock_mode=True)
        kfs = proc.generate_kfs("APP-KFS-001", loan_amount=500_000, tenure_months=36, annual_rate=14.0)

        assert kfs.loan_amount == 500_000
        assert kfs.emi > 0
        assert kfs.total_repayment > kfs.loan_amount
        assert kfs.apr > 0
        assert kfs.processing_fee > 0
        assert kfs.status == KFSStatus.GENERATED

    def test_kfs_disclosure_flow(self):
        proc = ComplianceProcessor(mock_mode=True)
        proc.generate_kfs("APP-KFS-002", 300_000, 24, 12.0)

        kfs = proc.disclose_kfs("APP-KFS-002")
        assert kfs.status == KFSStatus.DISCLOSED
        assert kfs.disclosed_at is not None

        kfs = proc.accept_kfs("APP-KFS-002")
        assert kfs.status == KFSStatus.ACCEPTED
        assert kfs.accepted_at is not None

    def test_cooling_off_period_allows_cancellation(self):
        proc = ComplianceProcessor(mock_mode=True)
        record = proc.start_cooling_off("APP-COOL-001")

        assert record.cancellation_status == CancellationStatus.ELIGIBLE

        cancelled = proc.cancel_within_cooling_off("APP-COOL-001")
        assert cancelled.cancellation_status == CancellationStatus.CANCELLED
        assert cancelled.cancelled_at is not None


class TestDataResidency:
    def test_india_endpoints_pass(self):
        results = ComplianceProcessor.check_data_residency({
            "postgresql": "postgresql://db.ap-south-1.rds.amazonaws.com:5432/loip",
            "minio": "http://minio.mumbai.internal:9000",
        })
        assert all(r.is_india_region for r in results)

    def test_non_india_endpoint_fails(self):
        results = ComplianceProcessor.check_data_residency({
            "postgresql": "postgresql://db.us-east-1.rds.amazonaws.com:5432/loip",
        })
        assert not results[0].is_india_region


class TestRBAC:
    def test_admin_has_all_permissions(self):
        user = AuthenticatedUser(user_id="admin", role=Role.ADMIN)
        assert user.has_permission("anything:here")

    def test_reviewer_can_override(self):
        user = AuthenticatedUser(user_id="rev1", role=Role.REVIEWER)
        assert user.has_permission("review:override")

    def test_reviewer_cannot_delete_data(self):
        user = AuthenticatedUser(user_id="rev1", role=Role.REVIEWER)
        assert not user.has_permission("compliance:delete")

    def test_compliance_officer_can_delete(self):
        user = AuthenticatedUser(user_id="co1", role=Role.COMPLIANCE_OFFICER)
        assert user.has_permission("compliance:delete")

    def test_api_consumer_limited_permissions(self):
        user = AuthenticatedUser(user_id="api1", role=Role.API_CONSUMER)
        assert user.has_permission("onboard:write")
        assert not user.has_permission("review:override")
        assert not user.has_permission("compliance:delete")


class TestMLOps:
    def test_register_and_promote_model(self):
        proc = MLOpsProcessor(mock_mode=True)
        model = proc.register_model("risk_xgboost", "1.0", {"auc_roc": 0.90, "f1_score": 0.85})

        assert model.stage == ModelStage.DEVELOPMENT

        gate = proc.promote_model("risk_xgboost", "1.0", ModelStage.PRODUCTION)
        assert gate.passed

        prod_models = proc.get_production_models()
        assert len(prod_models) == 1

    def test_promotion_blocked_by_gate(self):
        proc = MLOpsProcessor(mock_mode=True)
        proc.register_model("risk_xgboost", "2.0", {"auc_roc": 0.70, "f1_score": 0.65})

        gate = proc.promote_model("risk_xgboost", "2.0", ModelStage.PRODUCTION)
        assert not gate.passed

    def test_drift_detection_triggers_alert(self):
        proc = MLOpsProcessor(mock_mode=True)
        alert = proc.check_drift("risk_xgboost", DriftType.DATA_DRIFT, 0.25)

        assert alert is not None
        assert alert.drift_score == 0.25

    def test_no_alert_below_threshold(self):
        proc = MLOpsProcessor(mock_mode=True)
        alert = proc.check_drift("risk_xgboost", DriftType.DATA_DRIFT, 0.05)

        assert alert is None

    def test_high_drift_triggers_retraining(self):
        proc = MLOpsProcessor(mock_mode=True)
        proc.check_drift("risk_xgboost", DriftType.MODEL_DRIFT, 0.30)

        triggers = proc.get_retraining_triggers()
        assert len(triggers) == 1
        assert triggers[0].reason == "drift_alert"

    def test_feature_views_cover_all_domains(self):
        proc = MLOpsProcessor(mock_mode=True)
        views = proc.get_feature_views()
        domains = {v.domain for v in views}

        assert "identity" in domains
        assert "income" in domains
        assert "affordability" in domains
        assert "fraud" in domains
        assert "risk" in domains
