from loip.models.lightgbm_wrapper import LightGBMWrapper
from schemas.affordability import AffordabilityResult, AffordabilityFlag
from schemas.evidence import EvidenceChain, ReconciliationMethod

class AffordabilityProcessor:
    def __init__(self, mock_mode: bool = True):
        self.lgbm = LightGBMWrapper(mock_mode=mock_mode)

    def _compute_emi(self, principal: float, annual_rate: float, tenure_months: int) -> float:
        if tenure_months == 0: return 0.0
        r = annual_rate / 12 / 100
        if r == 0: return principal / tenure_months
        return principal * r * ((1+r)**tenure_months) / (((1+r)**tenure_months) - 1)

    def process_affordability(self, application_id: str, income_result: dict, application_data: dict, extracted_data: dict) -> AffordabilityResult:
        verified_monthly_income = income_result.get("verified_monthly_income", 0.0)
        income_confidence = income_result.get("income_confidence", 0.0)
        
        loan_amount = application_data.get("loan_amount", 0.0)
        tenure_months = application_data.get("tenure_months", 12)
        indicative_rate = application_data.get("interest_rate", 14.0) # default 14% p.a.
        
        proposed_emi = self._compute_emi(loan_amount, indicative_rate, tenure_months)
        
        # Parse existing obligations from bank statement (mocked for now)
        existing_obligations = 0.0
        if "bank_statement" in extracted_data:
            pass
            
        total_obligations = existing_obligations + proposed_emi
        
        foir = 0.0
        if verified_monthly_income > 0:
            foir = total_obligations / verified_monthly_income
            
        estimated_monthly_expenses = 15000.0 # Configurable
        disposable_income = verified_monthly_income - total_obligations - estimated_monthly_expenses
        
        liquidity_score = 0.8
        cashflow_stability = 0.8
        financial_stress_score = 0.1
        
        result = AffordabilityResult(
            application_id=application_id,
            verified_monthly_income=verified_monthly_income,
            income_confidence=income_confidence,
            income_evidence=income_result.get("evidence_chains", []),
            existing_obligations=existing_obligations,
            proposed_emi=proposed_emi,
            total_obligations=total_obligations,
            foir=min(foir, 1.0),
            dti=min(foir, 1.0),
            disposable_income=disposable_income,
            liquidity_score=liquidity_score,
            cashflow_stability=cashflow_stability,
            financial_stress_score=financial_stress_score,
            affordability_score=0.0,
            affordability_confidence=1.0
        )
        
        if result.foir > 0.60:
            result.anomaly_flags.append(AffordabilityFlag.FOIR_EXCEEDED)
        elif result.foir > 0.50:
            result.anomaly_flags.append(AffordabilityFlag.FOIR_MARGINAL)
            
        if disposable_income < 0:
            result.anomaly_flags.append(AffordabilityFlag.DISPOSABLE_INCOME_INSUFFICIENT)
            
        result.affordability_score = self.lgbm.predict({
            "foir": result.foir,
            "disposable_income": result.disposable_income,
            "liquidity_score": result.liquidity_score
        })

        result.evidence_chains.append(EvidenceChain(
            claim=f"foir={result.foir:.4f}",
            supporting=[],
            reconciled_value=result.foir,
            reconciliation_method=ReconciliationMethod.COMPUTED,
            confidence=result.affordability_confidence,
        ))

        return result
