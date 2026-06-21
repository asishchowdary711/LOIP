import json
import logging

from loip.models.xgboost_wrapper import XGBoostWrapper

logger = logging.getLogger(__name__)
from loip.schemas.evidence import (
    DocumentType,
    EvidenceChain,
    ExtractedField,
    ExtractionMethod,
    ReconciliationMethod,
    SourceLocation,
)
from loip.schemas.income import IncomeFlag, IncomeResult, IncomeSource, SalaryCredit


class IncomeIntelligenceProcessor:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self.xgboost = XGBoostWrapper(mock_mode=mock_mode)
        # Stamp the right model version on every SourceLocation so audit logs
        # can distinguish a real-extraction figure from a deterministic mock.
        self._model_version = "qwen2.5-vl-mock" if mock_mode else "qwen2.5-vl:3b"

    def _doc_source(
        self, doc_type: str, field_name: str, value: float | str,
        confidence: float, document_ids: dict | None,
    ) -> list[ExtractedField]:
        """Build a document-backed ExtractedField when the source document has
        been stored (``document_ids[doc_type]`` is a MinIO object id). Returns
        an empty list otherwise, so evidence chains stay valid without storage."""
        if not document_ids or doc_type not in document_ids:
            return []
        return [ExtractedField(
            field_name=field_name,
            raw_value=str(value),
            confidence=confidence,
            source=SourceLocation(
                document_id=document_ids[doc_type],
                document_type=DocumentType(doc_type),
                is_synthetic=self.mock_mode,
                extraction_method=ExtractionMethod.QWEN2_5_VL,
                model_version=self._model_version,
            ),
        )]

    def process_income(self, application_id: str, extracted_data: dict, segment: str = "salaried", application_employer_name: str | None = None, document_ids: dict | None = None, declared_monthly_income: float | None = None) -> IncomeResult:
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

        # Source-trust weights differ by segment (build-plan §6.3 salaried vs
        # §7.2 self-employed — tax documents are most authoritative).
        is_self_employed = segment == "self_employed"
        w_itr = 0.90 if is_self_employed else 0.85
        w_itr_fy2 = 0.80
        w_gst = 0.75
        w_bank = 0.65 if is_self_employed else 0.75
        gst_profit_margin = 0.25  # net income ≈ 25% of turnover (§7.2)

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
                            supporting=self._doc_source("salary_slip", "net_pay", salary_slip_amount, 0.9, document_ids),
                            reconciled_value=salary_slip_amount,
                            reconciliation_method=ReconciliationMethod.SOURCE_TRUST_WEIGHTED,
                            confidence=0.9
                        )
                    ))
            except ValueError:
                result.anomaly_flags.append(IncomeFlag.SALARY_MISSING_MANDATORY_FIELDS)

            slip_employer = slip.get("employer_name")
            if slip_employer and application_employer_name:
                if slip_employer.strip().lower() != application_employer_name.strip().lower():
                    result.anomaly_flags.append(IncomeFlag.EMPLOYER_NAME_MISMATCH)


        # 2. Parse ITR — current FY (and prior FY for 2-year averaging, §7.2)
        if "itr" in extracted_data:
            itr = extracted_data["itr"]
            try:
                itr_amount = float(itr.get("total_income", "0"))
                if itr_amount > 0:
                    result.income_sources.append(IncomeSource(
                        source_name="itr",
                        annual_amount=itr_amount,
                        trust_weight=w_itr,  # tax document — highest trust
                        evidence=EvidenceChain(
                            claim=f"itr_total_income={itr_amount}",
                            supporting=self._doc_source("itr", "total_income", itr_amount, 0.95, document_ids),
                            reconciled_value=itr_amount,
                            reconciliation_method=ReconciliationMethod.SOURCE_TRUST_WEIGHTED,
                            confidence=0.95
                        )
                    ))
            except ValueError:
                pass

        if "itr_fy2" in extracted_data:
            try:
                itr_fy2_amount = float(extracted_data["itr_fy2"].get("total_income", "0"))
                if itr_fy2_amount > 0:
                    result.income_sources.append(IncomeSource(
                        source_name="itr_fy2",
                        annual_amount=itr_fy2_amount,
                        trust_weight=w_itr_fy2,  # prior-year ITR, slightly lower weight
                        evidence=EvidenceChain(
                            claim=f"itr_fy2_total_income={itr_fy2_amount}",
                            supporting=self._doc_source("itr", "total_income", itr_fy2_amount, 0.9, document_ids),
                            reconciled_value=itr_fy2_amount,
                            reconciliation_method=ReconciliationMethod.SOURCE_TRUST_WEIGHTED,
                            confidence=0.9
                        )
                    ))
            except ValueError:
                pass

        # 3. Parse GST Returns — annual turnover * profit margin (§7.2 fallback
        #    when ITR is unavailable; otherwise a corroborating signal).
        if "gst_return" in extracted_data:
            gst = extracted_data["gst_return"]
            try:
                gst_b2b = float(gst.get("turnover_b2b", "0"))
                gst_b2c = float(gst.get("turnover_b2c", "0"))
                annual_turnover = gst_b2b + gst_b2c
                gst_amount = annual_turnover * gst_profit_margin
                if gst_amount > 0:
                    result.income_sources.append(IncomeSource(
                        source_name="gst_return",
                        annual_amount=gst_amount,
                        trust_weight=w_gst,
                        evidence=EvidenceChain(
                            claim=f"gst_implied_income={gst_amount}",
                            supporting=self._doc_source("gst_return", "turnover", gst_amount, 0.85, document_ids),
                            reconciled_value=gst_amount,
                            reconciliation_method=ReconciliationMethod.SOURCE_TRUST_WEIGHTED,
                            confidence=0.85
                        )
                    ))
            except ValueError:
                pass

        # 4. Parse Bank Statement
        if "bank_statement" in extracted_data:
            stmt = extracted_data["bank_statement"]
            raw_credits = stmt.get("salary_credits")
            if isinstance(raw_credits, str):
                # Qwen returns JSON-encoded array via the VL extractor.
                try:
                    raw_credits = json.loads(raw_credits)
                except (json.JSONDecodeError, ValueError):
                    raw_credits = None
            if isinstance(raw_credits, list) and raw_credits:
                # Belt-and-braces: filter out anything whose narration screams
                # "debit / loan EMI / charge" even if the VL model labelled it
                # as a credit. These are signals of money OUT, not income IN.
                _DEBIT_HINTS = ("emi", "loan", "loan repayment", "transfer out",
                                "withdrawal", "atm", "pos ", "charges", "charge ",
                                "gst", "interest debit", "bill pay", " dr ", " dr.",
                                "debit ", "fee")
                def _is_credit(c: dict) -> bool:
                    if not isinstance(c, dict) or "amount" not in c:
                        return False
                    try:
                        amt = float(str(c.get("amount", "0")).replace(",", ""))
                    except ValueError:
                        return False
                    if amt <= 0:
                        return False
                    narration = str(c.get("narration", "")).lower()
                    return not any(hint in narration for hint in _DEBIT_HINTS)
                credits = [SalaryCredit(**c) for c in raw_credits if _is_credit(c)]
                if not credits and raw_credits:
                    logger.info("Bank statement: filtered out %d non-credit transactions (EMI/debit/charges)", len(raw_credits))
            elif self.mock_mode and (salary_slip_amount or itr_amount):
                # Mock-mode demo convenience: when no transaction-level extraction
                # is available, fabricate a single credit matching the slip/ITR so
                # the deterministic mock path produces a clean approval. Disabled
                # in real mode so the pay-slip-vs-bank check can actually fire.
                best_amount = salary_slip_amount or (itr_amount / 12)
                credits = [
                    SalaryCredit(amount=best_amount, date="01/01/2026", narration="CREDIT")
                ]
            else:
                # No corroborating income document — flag it rather than fabricating a number.
                credits = []
            result.salary_credits = credits
            if credits:
                bank_credit_amount = sum(c.amount for c in credits) / len(credits)
                result.income_sources.append(IncomeSource(
                    source_name="bank_statement",
                    annual_amount=bank_credit_amount * 12,
                    trust_weight=w_bank,
                    evidence=EvidenceChain(
                        claim=f"bank_avg_credit={bank_credit_amount}",
                        supporting=self._doc_source("bank_statement", "salary_credit", bank_credit_amount, 0.9, document_ids),
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
                if salary_slip_amount > bank_credit_amount:
                    result.anomaly_flags.append(IncomeFlag.INCOME_INFLATION)

        if result.verified_monthly_income > 0 and result.verified_monthly_income < 20000:
            result.anomaly_flags.append(IncomeFlag.INCOME_BELOW_RBI_MINIMUM)

        # Compare the applicant's typed declaration against what the documents
        # actually show. Beyond 10% delta the application must be reviewed —
        # the verified number from documents wins downstream, but the form
        # mismatch is a strong signal of mis-statement or fraud.
        if (
            declared_monthly_income is not None
            and declared_monthly_income > 0
            and result.verified_monthly_income > 0
        ):
            delta = abs(declared_monthly_income - result.verified_monthly_income) / max(
                declared_monthly_income, result.verified_monthly_income
            )
            if delta > 0.10:
                result.anomaly_flags.append(IncomeFlag.INCOME_DECLARATION_MISMATCH)
                if declared_monthly_income > result.verified_monthly_income:
                    result.anomaly_flags.append(IncomeFlag.INCOME_INFLATION)
                else:
                    result.anomaly_flags.append(IncomeFlag.INCOME_DEFLATION)

        # ML Confidence Scoring
        result.income_confidence = self.xgboost.predict({
            "salary_slip_amount": salary_slip_amount,
            "bank_credit_amount": bank_credit_amount,
            "anomalies": len(result.anomaly_flags)
        }, task="income_confidence")

        result.evidence_chains = [source.evidence for source in result.income_sources]

        return result
