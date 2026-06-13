"""CIBIL TransUnion credit report API client.

Primary credit bureau for Indian personal loan decisioning.
Pulls credit score (300-900), active loans, overdue accounts,
and DPD 90+ flag. Hard gate: score < 650 → auto-reject.

Consent check: credit_bureau_consent must exist in consent_records
before this API is called (DPDP Act + RBI DLG compliance).
"""

from __future__ import annotations

from schemas.bureau import CreditBureauResult
from schemas.evidence import (
    EvidenceChain,
    ReconciliationMethod,
)

from .base import BaseClient, ConsentRequiredError, IntegrationError


class CIBILClient(BaseClient):
    service_name = "cibil"
    env_prefix = "CIBIL"

    async def fetch_report(
        self,
        pan: str,
        dob: str,
        name: str,
        application_id: str,
        consent_verified: bool = False,
    ) -> CreditBureauResult:
        """Fetch CIBIL credit report.

        Args:
            pan: PAN number (used as primary key by CIBIL)
            dob: Date of birth DD/MM/YYYY
            name: Full name as on PAN
            application_id: LOIP application ID for traceability
            consent_verified: Caller must set True after confirming consent exists
        """
        if not consent_verified:
            raise ConsentRequiredError("cibil", "credit_bureau_pull")

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
            bureau="cibil",
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
            bureau="cibil",
            score=750,
            active_loans=2,
            overdue_accounts=0,
            dpd_90_plus=False,
            total_outstanding=450000.0,
            enquiry_count_last_6m=1,
            evidence=self._build_evidence(750),
        )

    def _build_evidence(self, score: int) -> EvidenceChain:
        return EvidenceChain(
            claim=f"cibil_score={score}",
            supporting=[],
            reconciled_value=score,
            reconciliation_method=ReconciliationMethod.API_AUTHORITATIVE,
            confidence=1.0,
        )
