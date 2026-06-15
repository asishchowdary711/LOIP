from loip.domains.identity_trust.vcip import VCIPProcessor
from loip.models.xgboost_wrapper import XGBoostWrapper
from loip.schemas.affordability import AffordabilityResult
from loip.schemas.bureau import CreditBureauResult
from loip.schemas.decision import (
    OnboardingDecision, Decision, ReasonCode, LoanApplication
)
from loip.schemas.identity import IdentityVerificationResult, IdentityFlag
from loip.schemas.income import IncomeResult, IncomeFlag
from loip.schemas.vcip import VCIPResult, VCIPStatus

class RiskDecisionProcessor:
    def __init__(self, mock_mode: bool = True):
        self.ensemble = XGBoostWrapper(mock_mode=mock_mode)

    def decide(
        self,
        application: LoanApplication,
        identity: IdentityVerificationResult,
        income: IncomeResult,
        affordability: AffordabilityResult,
        bureau: CreditBureauResult,
        fraud: dict = None,
        vcip: VCIPResult | None = None,
    ) -> OnboardingDecision:

        reason_codes = []
        review_flags = []

        # RBI V-CIP gate: video KYC must be completed before disbursal for
        # loans above the configured ceiling. A failed V-CIP is a hard reject;
        # an incomplete/absent one blocks disbursal (handled at the approve gate).
        vcip_required = VCIPProcessor.is_required(application.loan_amount)
        vcip_completed = vcip is not None and vcip.status == VCIPStatus.COMPLETED
        disbursal_blocked = vcip_required and not vcip_completed
        disbursal_block_reason = "vcip_required_not_completed" if disbursal_blocked else None

        # 0. Hard Fraud Rejects
        if fraud and fraud.fraud_score > 0.80:
            reason_codes.append(ReasonCode(code="high_fraud_risk", category="risk", detail=f"score={fraud.fraud_score}"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes, fraud=fraud)

        # 0b. Hard V-CIP reject — a failed video-KYC session is a regulatory reject
        if vcip is not None and vcip.status == VCIPStatus.FAILED:
            detail = ",".join(f.value for f in vcip.flags) or None
            reason_codes.append(ReasonCode(code="vcip_failed", category="identity", detail=detail))
            return self._reject(application, identity, income, affordability, bureau, reason_codes, fraud=fraud)

        # 1. Hard KYC Rejects
        if identity.identity_confidence < 0.30:
            reason_codes.append(ReasonCode(code="identity_low_confidence", category="identity"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes, fraud=fraud)

        if identity.has_flag(IdentityFlag.PAN_NSDL_INACTIVE):
            reason_codes.append(ReasonCode(code="pan_inactive_or_invalid", category="identity"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes, fraud=fraud)

        if identity.has_flag(IdentityFlag.AADHAAR_OTP_FAILED):
            reason_codes.append(ReasonCode(code="aadhaar_verification_failed", category="identity"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes, fraud=fraud)

        if identity.has_flag(IdentityFlag.PAN_FORMAT_INVALID) or identity.has_flag(IdentityFlag.AADHAAR_FORMAT_INVALID):
            reason_codes.append(ReasonCode(code="kyc_document_invalid", category="identity"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes, fraud=fraud)

        if identity.has_flag(IdentityFlag.NAME_PAN_AADHAAR_MISMATCH):
            reason_codes.append(ReasonCode(code="identity_mismatch_name", category="identity"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes, fraud=fraud)

        if identity.has_flag(IdentityFlag.DOB_MISMATCH):
            reason_codes.append(ReasonCode(code="identity_mismatch_dob", category="identity"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes, fraud=fraud)

        # 2. Hard Credit Rejects
        if bureau.score < 650:
            reason_codes.append(ReasonCode(code="cibil_score_below_minimum", category="credit", detail=f"score={bureau.score}"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes, fraud=fraud)

        if bureau.dpd_90_plus:
            reason_codes.append(ReasonCode(code="dpd_90_plus_in_24_months", category="credit"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes, fraud=fraud)

        if bureau.overdue_accounts > 0:
            reason_codes.append(ReasonCode(code="overdue_accounts_in_bureau", category="credit"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes, fraud=fraud)

        # 3. Hard Income Rejects
        if income.segment == "salaried" and IncomeFlag.NO_SALARY_CREDIT_FOUND in income.anomaly_flags:
            reason_codes.append(ReasonCode(code="bank_credit_not_found", category="income"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes, fraud=fraud)

        # 4. Hard Affordability Rejects
        if affordability.foir > 0.60:
            reason_codes.append(ReasonCode(code="foir_exceeded", category="affordability", detail=f"foir={affordability.foir:.2f}"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes, fraud=fraud)

        if income.verified_monthly_income < application.min_income_requirement:
            reason_codes.append(ReasonCode(code="income_below_minimum", category="income"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes, fraud=fraud)

        # 5. Review Triggers
        if identity.identity_confidence < 0.70:
            review_flags.append("identity_moderate_confidence")
        if identity.has_flag(IdentityFlag.DOCUMENT_METADATA_ANOMALY):
            review_flags.append("document_metadata_anomaly")
        if affordability.foir > 0.50:
            review_flags.append(f"foir_marginal:{affordability.foir:.2f}")
        if income.anomaly_flags:
            review_flags.append(f"income_anomalies:{','.join(income.anomaly_flags)}")
        if affordability.anomaly_flags:
            review_flags.append(f"affordability_anomalies:{','.join(affordability.anomaly_flags)}")
        if bureau.score < 700:
            review_flags.append(f"cibil_marginal:{bureau.score}")
        if bureau.active_loans > 3:
            review_flags.append(f"multiple_active_loans:{bureau.active_loans}")
        if application.employment_tier >= 4:
            review_flags.append(f"employment_tier_high_risk:{application.employment_tier}")

        if review_flags:
            if disbursal_blocked:
                review_flags.append("vcip_pending")
            return self._review(application, identity, income, affordability, bureau, review_flags, fraud=fraud,
                                disbursal_blocked=disbursal_blocked, disbursal_block_reason=disbursal_block_reason)

        # 5. Soft ML Scoring
        score = self.ensemble.predict({
            "identity_confidence": identity.identity_confidence,
            "income_confidence": income.income_confidence,
            "foir": affordability.foir,
            "cibil_score_normalized": max(0.0, (bureau.score - 300) / 600),
            "cashflow_stability": affordability.cashflow_stability,
            "employment_tier": application.employment_tier,
            "loan_to_income_ratio": application.loan_amount / max(1, (income.verified_monthly_income * 12))
        }, task="risk_score")

        if score >= 0.70:
            # Risk-approvable, but a required-yet-incomplete V-CIP holds disbursal:
            # downgrade to REVIEW pending video KYC rather than auto-approve.
            if disbursal_blocked:
                review_flags.append("vcip_pending")
                return self._review(application, identity, income, affordability, bureau, review_flags, score, fraud=fraud,
                                    disbursal_blocked=True, disbursal_block_reason=disbursal_block_reason)
            return self._approve(application, identity, income, affordability, bureau, score, fraud=fraud)
        elif score >= 0.40:
            review_flags.append("borderline_score")
            if disbursal_blocked:
                review_flags.append("vcip_pending")
            return self._review(application, identity, income, affordability, bureau, review_flags, score, fraud=fraud,
                                disbursal_blocked=disbursal_blocked, disbursal_block_reason=disbursal_block_reason)
        else:
            reason_codes.append(ReasonCode(code="low_ensemble_score", category="risk"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes, score, fraud=fraud)

    def _evidence_chains(self, idn, inc, aff, fraud=None):
        chains = list(idn.evidence_chains) + list(inc.evidence_chains) + list(aff.evidence_chains)
        if fraud is not None:
            chains += list(fraud.evidence_chains)
        return chains

    def _reject(self, app, idn, inc, aff, bur, reasons, score=None, fraud=None):
        return OnboardingDecision(
            application_id=app.application_id,
            decision=Decision.REJECT,
            loan_amount=app.loan_amount,
            reason_codes=reasons,
            risk_score=score,
            identity_result=idn,
            income_result=inc,
            affordability_result=aff,
            bureau_result=bur,
            evidence_chains=self._evidence_chains(idn, inc, aff, fraud)
        )

    def _review(self, app, idn, inc, aff, bur, flags, score=None, fraud=None,
                disbursal_blocked=False, disbursal_block_reason=None):
        return OnboardingDecision(
            application_id=app.application_id,
            decision=Decision.REVIEW,
            loan_amount=app.loan_amount,
            review_flags=flags,
            risk_score=score,
            disbursal_blocked=disbursal_blocked,
            disbursal_block_reason=disbursal_block_reason,
            identity_result=idn,
            income_result=inc,
            affordability_result=aff,
            bureau_result=bur,
            evidence_chains=self._evidence_chains(idn, inc, aff, fraud)
        )

    def _approve(self, app, idn, inc, aff, bur, score, fraud=None):
        return OnboardingDecision(
            application_id=app.application_id,
            decision=Decision.APPROVE,
            loan_amount=app.loan_amount,
            risk_score=score,
            identity_result=idn,
            income_result=inc,
            affordability_result=aff,
            bureau_result=bur,
            evidence_chains=self._evidence_chains(idn, inc, aff, fraud)
        )
