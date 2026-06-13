"""Experian India credit report API client (fallback bureau).

Used when CIBIL is unavailable or as a secondary bureau pull for
cross-validation. Same consent requirements as CIBIL.
"""

from __future__ import annotations

from schemas.bureau import CreditBureauResult
from schemas.evidence import (
    EvidenceChain,
    ReconciliationMethod,
)

from .base import BaseClient, ConsentRequiredError, IntegrationError


class ExperianClient(BaseClient):
    service_name = "experian"
    env_prefix = "EXPERIAN"

    async def fetch_report(
        self,
        pan: str,
        dob: str,
        name: str,
        application_id: str,
        consent_verified: bool = False,
    ) -> CreditBureauResult:
        """Fetch Experian India credit report (fallback to CIBIL).

        Args:
            pan: PAN number
            dob: Date of birth DD/MM/YYYY
            name: Full name as on PAN
            application_id: LOIP application ID for traceability
            consent_verified: Caller must set True after confirming consent exists
        """
        if not consent_verified:
            raise ConsentRequiredError("experian", "credit_bureau_pull")

        if self._mock:
            return self._mock_response(pan, application_id)

        try:
            data = await self._request("POST", "", json_body={
                "pan": pan,
                "dob": dob,
                "name": name,
            })
        except IntegrationError:
            raise

        return CreditBureauResult(
            application_id=application_id,
            bureau="experian",
            score=data["score"],
            active_loans=data.get("active_loans_count", 0),
            overdue_accounts=data.get("overdue_count", 0),
            dpd_90_plus=data.get("dpd_90_plus_flag", False),
            total_outstanding=data.get("total_outstanding", 0.0),
            enquiry_count_last_6m=data.get("enquiry_count_6m", 0),
            evidence=self._build_evidence(data["score"]),
        )

    def _mock_response(self, pan: str, application_id: str) -> CreditBureauResult:
        return CreditBureauResult(
            application_id=application_id,
            bureau="experian",
            score=740,
            active_loans=1,
            overdue_accounts=0,
            dpd_90_plus=False,
            total_outstanding=320000.0,
            enquiry_count_last_6m=2,
            evidence=self._build_evidence(740),
        )

    def _build_evidence(self, score: int) -> EvidenceChain:
        return EvidenceChain(
            claim=f"experian_score={score}",
            supporting=[],
            reconciled_value=score,
            reconciliation_method=ReconciliationMethod.API_AUTHORITATIVE,
            confidence=1.0,
        )
