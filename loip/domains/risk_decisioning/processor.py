from loip.models.xgboost_wrapper import XGBoostWrapper
from schemas.decision import (
    OnboardingDecision, Decision, ReasonCode, LoanApplication
)
from schemas.identity import IdentityVerificationResult, IdentityFlag
from schemas.income import IncomeResult
from schemas.affordability import AffordabilityResult
from schemas.bureau import CreditBureauResult

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
        fraud: dict = None
    ) -> OnboardingDecision:
        
        reason_codes = []
        review_flags = []
        
        # 0. Hard Fraud Rejects
        if fraud and fraud.fraud_score > 0.80:
            reason_codes.append(ReasonCode(code="high_fraud_risk", category="risk", detail=f"score={fraud.fraud_score}"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes)
        
        # 1. Hard KYC Rejects
        if identity.identity_confidence < 0.30:
            reason_codes.append(ReasonCode(code="identity_low_confidence", category="identity"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes)
            
        if identity.has_flag(IdentityFlag.PAN_NSDL_INACTIVE):
            reason_codes.append(ReasonCode(code="pan_inactive_or_invalid", category="identity"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes)
            
        if identity.has_flag(IdentityFlag.AADHAAR_OTP_FAILED):
            reason_codes.append(ReasonCode(code="aadhaar_verification_failed", category="identity"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes)
            
        if identity.has_flag(IdentityFlag.PAN_FORMAT_INVALID) or identity.has_flag(IdentityFlag.AADHAAR_FORMAT_INVALID):
            reason_codes.append(ReasonCode(code="kyc_document_invalid", category="identity"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes)

        # 2. Hard Credit Rejects
        if bureau.score < 650:
            reason_codes.append(ReasonCode(code="cibil_score_below_minimum", category="credit", detail=f"score={bureau.score}"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes)
            
        if bureau.dpd_90_plus:
            reason_codes.append(ReasonCode(code="dpd_90_plus_in_24_months", category="credit"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes)
            
        if bureau.overdue_accounts > 0:
            reason_codes.append(ReasonCode(code="overdue_accounts_in_bureau", category="credit"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes)

        # 3. Hard Affordability Rejects
        if affordability.foir > 0.60:
            reason_codes.append(ReasonCode(code="foir_exceeded", category="affordability", detail=f"foir={affordability.foir:.2f}"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes)
            
        if income.verified_monthly_income < application.min_income_requirement:
            reason_codes.append(ReasonCode(code="income_below_minimum", category="income"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes)

        # 4. Review Triggers
        if identity.identity_confidence < 0.70:
            review_flags.append("identity_moderate_confidence")
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
            return self._review(application, identity, income, affordability, bureau, review_flags)

        # 5. Soft ML Scoring
        score = self.ensemble.predict({
            "identity_confidence": identity.identity_confidence,
            "income_confidence": income.income_confidence,
            "foir": affordability.foir,
            "cibil_score_normalized": max(0.0, (bureau.score - 300) / 600),
            "cashflow_stability": affordability.cashflow_stability,
            "employment_tier": application.employment_tier,
            "loan_to_income_ratio": application.loan_amount / max(1, (income.verified_monthly_income * 12))
        })
        
        if score >= 0.70:
            return self._approve(application, identity, income, affordability, bureau, score)
        elif score >= 0.40:
            review_flags.append("borderline_score")
            return self._review(application, identity, income, affordability, bureau, review_flags, score)
        else:
            reason_codes.append(ReasonCode(code="low_ensemble_score", category="risk"))
            return self._reject(application, identity, income, affordability, bureau, reason_codes, score)

    def _reject(self, app, idn, inc, aff, bur, reasons, score=None):
        return OnboardingDecision(
            application_id=app.application_id,
            decision=Decision.REJECT,
            reason_codes=reasons,
            risk_score=score,
            identity_result=idn,
            income_result=inc,
            affordability_result=aff,
            bureau_result=bur
        )

    def _review(self, app, idn, inc, aff, bur, flags, score=None):
        return OnboardingDecision(
            application_id=app.application_id,
            decision=Decision.REVIEW,
            review_flags=flags,
            risk_score=score,
            identity_result=idn,
            income_result=inc,
            affordability_result=aff,
            bureau_result=bur
        )

    def _approve(self, app, idn, inc, aff, bur, score):
        return OnboardingDecision(
            application_id=app.application_id,
            decision=Decision.APPROVE,
            risk_score=score,
            identity_result=idn,
            income_result=inc,
            affordability_result=aff,
            bureau_result=bur
        )
