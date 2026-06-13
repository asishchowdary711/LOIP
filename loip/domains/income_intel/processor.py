from loip.models.xgboost_wrapper import XGBoostWrapper
from schemas.income import (
    IncomeResult, IncomeSource, SalaryCredit, IncomeFlag
)
from schemas.evidence import EvidenceChain, ReconciliationMethod

class IncomeIntelligenceProcessor:
    def __init__(self, mock_mode: bool = True):
        self.xgboost = XGBoostWrapper(mock_mode=mock_mode)

    def process_income(self, application_id: str, extracted_data: dict, segment: str = "salaried") -> IncomeResult:
        result = IncomeResult(
            application_id=application_id, 
            segment=segment,
            reconciled_annual_income=0.0,
            verified_monthly_income=0.0,
            income_confidence=1.0
        )
        
        salary_slip_amount = 0.0
        bank_credit_amount = 0.0
        itr_amount = 0.0
        gst_amount = 0.0
        
        # 1. Parse Salary Slip
        if "salary_slip" in extracted_data:
            slip = extracted_data["salary_slip"]
            try:
                salary_slip_amount = float(slip.get("net_pay", "0"))
                if salary_slip_amount > 0:
                    result.income_sources.append(IncomeSource(
                        source_name="salary_slip",
                        annual_amount=salary_slip_amount * 12,
                        trust_weight=0.65,
                        evidence=EvidenceChain(
                            claim=f"salary_slip_net_pay={salary_slip_amount}",
                            supporting=[],
                            reconciled_value=salary_slip_amount,
                            reconciliation_method=ReconciliationMethod.SOURCE_TRUST_WEIGHTED,
                            confidence=0.9
                        )
                    ))
            except ValueError:
                result.anomaly_flags.append(IncomeFlag.SALARY_MISSING_MANDATORY_FIELDS)
                
        # 2. Parse ITR
        if "itr" in extracted_data:
            itr = extracted_data["itr"]
            try:
                itr_amount = float(itr.get("total_income", "0"))
                if itr_amount > 0:
                    result.income_sources.append(IncomeSource(
                        source_name="itr",
                        annual_amount=itr_amount,
                        trust_weight=0.85,  # ITR is very high trust
                        evidence=EvidenceChain(
                            claim=f"itr_total_income={itr_amount}",
                            supporting=[],
                            reconciled_value=itr_amount,
                            reconciliation_method=ReconciliationMethod.SOURCE_TRUST_WEIGHTED,
                            confidence=0.95
                        )
                    ))
            except ValueError:
                pass
                
        # 3. Parse GST Returns
        if "gst_return" in extracted_data:
            gst = extracted_data["gst_return"]
            try:
                gst_b2b = float(gst.get("turnover_b2b", "0"))
                gst_b2c = float(gst.get("turnover_b2c", "0"))
                gst_amount = (gst_b2b + gst_b2c) * 0.10 # Assuming 10% margin as income
                if gst_amount > 0:
                    result.income_sources.append(IncomeSource(
                        source_name="gst_return",
                        annual_amount=gst_amount * 12, # assuming monthly return, annualize it
                        trust_weight=0.70,
                        evidence=EvidenceChain(
                            claim=f"gst_implied_income={gst_amount * 12}",
                            supporting=[],
                            reconciled_value=gst_amount * 12,
                            reconciliation_method=ReconciliationMethod.SOURCE_TRUST_WEIGHTED,
                            confidence=0.85
                        )
                    ))
            except ValueError:
                pass
                
        # 4. Parse Bank Statement
        if "bank_statement" in extracted_data:
            stmt = extracted_data["bank_statement"]
            # Mocking salary credit detection or cash flow for self-employed
            credits = [
                SalaryCredit(amount=salary_slip_amount or (itr_amount/12) or 50000.0, date="01/01/2026", narration="CREDIT")
            ]
            result.salary_credits = credits
            if credits:
                bank_credit_amount = sum(c.amount for c in credits) / len(credits)
                result.income_sources.append(IncomeSource(
                    source_name="bank_statement",
                    annual_amount=bank_credit_amount * 12,
                    trust_weight=0.75,
                    evidence=EvidenceChain(
                        claim=f"bank_avg_credit={bank_credit_amount}",
                        supporting=[],
                        reconciled_value=bank_credit_amount,
                        reconciliation_method=ReconciliationMethod.SOURCE_TRUST_WEIGHTED,
                        confidence=0.9
                    )
                ))
            else:
                if segment == "salaried":
                    result.anomaly_flags.append(IncomeFlag.NO_SALARY_CREDIT_FOUND)

        # 5. Source Trust Weighting
        if result.income_sources:
            total_weight = sum(s.trust_weight for s in result.income_sources)
            weighted_sum = sum(s.annual_amount * s.trust_weight for s in result.income_sources)
            result.reconciled_annual_income = weighted_sum / total_weight
            result.verified_monthly_income = result.reconciled_annual_income / 12
        else:
            result.income_confidence = 0.0

        # Anomaly Detection
        if salary_slip_amount and bank_credit_amount:
            diff = abs(salary_slip_amount - bank_credit_amount)
            max_val = max(salary_slip_amount, bank_credit_amount)
            if max_val > 0 and diff / max_val > 0.3:
                result.anomaly_flags.append(IncomeFlag.SALARY_SLIP_VS_BANK_MISMATCH)

        if result.verified_monthly_income > 0 and result.verified_monthly_income < 20000:
            result.anomaly_flags.append(IncomeFlag.INCOME_BELOW_RBI_MINIMUM)

        # ML Confidence Scoring
        result.income_confidence = self.xgboost.predict({
            "salary_slip_amount": salary_slip_amount,
            "bank_credit_amount": bank_credit_amount,
            "anomalies": len(result.anomaly_flags)
        })

        return result
