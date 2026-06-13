"""Qwen3-32B reviewer copilot — generates human-readable case narratives for underwriter review."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from loip.domains.explainability.schemas import CopilotNarrative

logger = logging.getLogger(__name__)

COPILOT_SYSTEM_PROMPT = (
    "You are a personal loan underwriting assistant for an Indian NBFC. "
    "You review loan onboarding cases and produce concise, evidence-based assessments."
)

COPILOT_USER_TEMPLATE = """Review the following loan application case and produce a JSON response with exactly these keys:
- "profile_summary": A 3-sentence plain-English summary of the applicant's profile
- "primary_decision_reason": The single most important reason for the system's decision
- "inconsistencies": Up to 3 inconsistencies or red flags, each citing the source document (as a list of strings)
- "reviewer_questions": 2 specific questions for the human reviewer to verify (as a list of strings)

Application:
  Applicant: {applicant_name}
  Loan Amount: INR {loan_amount:,.0f}
  Tenure: {tenure_months} months
  Employment: {employment_type} (Tier {employment_tier})
  Employer: {employer_name}

Identity Verification:
  Confidence: {identity_confidence:.0%}
  PAN Verified: {pan_verified}
  Aadhaar Verified: {aadhaar_verified}
  Flags: {identity_flags}

Income Assessment:
  Verified Monthly Income: INR {verified_monthly_income:,.0f}
  Income Confidence: {income_confidence:.0%}
  Anomaly Flags: {income_flags}

Affordability:
  FOIR: {foir:.0%}
  Existing Obligations: INR {existing_obligations:,.0f}/month
  Proposed EMI: INR {proposed_emi:,.0f}/month
  Disposable Income: INR {disposable_income:,.0f}/month
  Cashflow Stability: {cashflow_stability:.0%}

Credit Bureau:
  CIBIL Score: {cibil_score}
  Active Loans: {active_loans}
  Overdue Accounts: {overdue_accounts}

System Decision: {decision}
Reason Codes: {reason_codes}
Review Flags: {review_flags}

Respond ONLY with valid JSON, no other text."""


class ReviewerCopilot:
    def __init__(self, mock_mode: bool = True, base_url: str = "http://localhost:8000/v1"):
        self.mock_mode = mock_mode
        self.base_url = base_url
        self.model_id = "qwen3-32b"

    async def generate_narrative(self, case_data: dict[str, Any]) -> CopilotNarrative:
        prompt = self._build_prompt(case_data)
        if self.mock_mode:
            return self._mock_narrative(case_data, prompt)
        return await self._call_llm(prompt)

    def _build_prompt(self, case_data: dict[str, Any]) -> str:
        app = case_data.get("application", {})
        identity = case_data.get("identity", {})
        income = case_data.get("income", {})
        affordability = case_data.get("affordability", {})
        bureau = case_data.get("bureau", {})
        decision = case_data.get("decision", {})

        return COPILOT_USER_TEMPLATE.format(
            applicant_name=app.get("applicant_name", "Unknown"),
            loan_amount=app.get("loan_amount", 0),
            tenure_months=app.get("tenure_months", 0),
            employment_type=app.get("employment_type", "unknown"),
            employment_tier=app.get("employment_tier", 0),
            employer_name=app.get("employer_name", "Not provided"),
            identity_confidence=identity.get("identity_confidence", 0),
            pan_verified=identity.get("pan_verified", False),
            aadhaar_verified=identity.get("aadhaar_verified", False),
            identity_flags=", ".join(identity.get("tamper_flags", [])) or "None",
            verified_monthly_income=income.get("verified_monthly_income", 0),
            income_confidence=income.get("income_confidence", 0),
            income_flags=", ".join(income.get("anomaly_flags", [])) or "None",
            foir=affordability.get("foir", 0),
            existing_obligations=affordability.get("existing_obligations", 0),
            proposed_emi=affordability.get("proposed_emi", 0),
            disposable_income=affordability.get("disposable_income", 0),
            cashflow_stability=affordability.get("cashflow_stability", 0),
            cibil_score=bureau.get("score", 0),
            active_loans=bureau.get("active_loans", 0),
            overdue_accounts=bureau.get("overdue_accounts", 0),
            decision=decision.get("decision", "unknown"),
            reason_codes=", ".join(r.get("code", "") for r in decision.get("reason_codes", [])) or "None",
            review_flags=", ".join(decision.get("review_flags", [])) or "None",
        )

    async def _call_llm(self, prompt: str) -> CopilotNarrative:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json={
                        "model": self.model_id,
                        "messages": [
                            {"role": "system", "content": COPILOT_SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 1024,
                    },
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return CopilotNarrative(
                    profile_summary=parsed["profile_summary"],
                    primary_decision_reason=parsed["primary_decision_reason"],
                    inconsistencies=parsed.get("inconsistencies", [])[:3],
                    reviewer_questions=parsed.get("reviewer_questions", [])[:2],
                    raw_prompt=prompt,
                    model_id=self.model_id,
                )
        except Exception:
            logger.warning("Qwen3 copilot call failed; returning fallback narrative", exc_info=True)
            return CopilotNarrative(
                profile_summary="Copilot narrative generation failed. Please review case manually.",
                primary_decision_reason="Unable to generate — LLM service unavailable.",
                inconsistencies=[],
                reviewer_questions=["Review all extracted fields manually.", "Cross-check income documents against bank statement."],
                raw_prompt=prompt,
                model_id=f"{self.model_id}-fallback",
            )

    def _mock_narrative(self, case_data: dict[str, Any], prompt: str) -> CopilotNarrative:
        app = case_data.get("application", {})
        income = case_data.get("income", {})
        affordability = case_data.get("affordability", {})
        bureau = case_data.get("bureau", {})
        decision = case_data.get("decision", {})
        decision_val = decision.get("decision", "review")

        name = app.get("applicant_name", "the applicant")
        loan_amt = app.get("loan_amount", 0)
        monthly_income = income.get("verified_monthly_income", 0)
        cibil = bureau.get("score", 0)
        foir = affordability.get("foir", 0)

        summary = (
            f"{name} has applied for a personal loan of INR {loan_amt:,.0f}. "
            f"Verified monthly income is INR {monthly_income:,.0f} with a CIBIL score of {cibil}. "
            f"The FOIR stands at {foir:.0%}, indicating {'comfortable' if foir <= 0.50 else 'stretched'} repayment capacity."
        )

        reason_map = {
            "approve": f"Strong credit profile (CIBIL {cibil}) with comfortable FOIR ({foir:.0%}).",
            "review": f"Marginal indicators require human verification — FOIR {foir:.0%}, CIBIL {cibil}.",
            "reject": f"Application fails hard gate: {', '.join(r.get('code', '') for r in decision.get('reason_codes', [])) or 'low ensemble score'}.",
        }

        inconsistencies = []
        income_flags = income.get("anomaly_flags", [])
        if income_flags:
            inconsistencies.append(f"Income anomaly detected: {income_flags[0]} (source: salary slip vs bank statement)")
        if foir > 0.50:
            inconsistencies.append(f"FOIR at {foir:.0%} exceeds comfortable threshold of 50% (source: affordability computation)")
        identity_flags = case_data.get("identity", {}).get("tamper_flags", [])
        if identity_flags:
            inconsistencies.append(f"Identity flag: {identity_flags[0]} (source: KYC verification)")

        return CopilotNarrative(
            profile_summary=summary,
            primary_decision_reason=reason_map.get(decision_val, "Decision requires manual review."),
            inconsistencies=inconsistencies[:3],
            reviewer_questions=[
                "Does the employer name on salary slips match the declared employer exactly?",
                "Are the bank statement salary credits consistent with the declared monthly income?",
            ],
            raw_prompt=prompt,
            model_id=f"{self.model_id}-mock",
        )
