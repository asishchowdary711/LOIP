"""UIDAI Aadhaar OTP eKYC API client.

Performs Aadhaar verification via OTP-based eKYC. Two-step flow:
  1. Request OTP → UIDAI sends OTP to Aadhaar-linked mobile
  2. Verify OTP → Returns demographic data (name, dob, gender, address)

DPDP Act 2023 compliance: explicit consent must be captured and stored
in consent_records before calling verify_otp. The client checks for
consent but does not enforce it — the pipeline layer must enforce.
"""

from __future__ import annotations

from schemas.evidence import (
    EvidenceChain,
    ExtractionMethod,
    ReconciliationMethod,
)
from schemas.identity import APIVerificationResult

from .base import BaseClient, ConsentRequiredError, IntegrationError


class UIDAIClient(BaseClient):
    service_name = "uidai"
    env_prefix = "UIDAI"

    async def request_otp(self, aadhaar_number: str) -> dict:
        """Request OTP to be sent to Aadhaar-linked mobile number.

        Returns a transaction ID to use in the verify step.
        """
        if len(aadhaar_number) != 12 or not aadhaar_number.isdigit():
            raise IntegrationError("uidai", "Aadhaar must be 12 digits")

        if self._mock:
            return {"txn_id": f"mock-txn-{aadhaar_number[:4]}", "status": "otp_sent"}

        data = await self._request("POST", "otp/request", json_body={
            "aadhaar": aadhaar_number,
        })
        return data

    async def verify_otp(
        self,
        aadhaar_number: str,
        otp: str,
        txn_id: str,
        consent_verified: bool = False,
    ) -> APIVerificationResult:
        """Verify OTP and retrieve eKYC demographic data.

        Args:
            aadhaar_number: 12-digit Aadhaar number
            otp: OTP received on Aadhaar-linked mobile
            txn_id: Transaction ID from request_otp step
            consent_verified: Caller must set True after confirming consent exists
        """
        if not consent_verified:
            raise ConsentRequiredError("uidai", "kyc_verification")

        if self._mock:
            return self._mock_response(aadhaar_number)

        try:
            data = await self._request("POST", "otp/verify", json_body={
                "aadhaar": aadhaar_number,
                "otp": otp,
                "txn_id": txn_id,
            })
        except IntegrationError:
            raise

        verified = data.get("verified", False)
        return APIVerificationResult(
            source="uidai_api",
            matched=verified,
            status="verified" if verified else "otp_failed",
            raw_response=data,
            evidence=self._build_evidence(aadhaar_number, verified),
        )

    def _mock_response(self, aadhaar: str) -> APIVerificationResult:
        masked = "XXXX-XXXX-" + aadhaar[-4:]
        return APIVerificationResult(
            source="uidai_api",
            matched=True,
            status="verified",
            raw_response={
                "aadhaar_masked": masked,
                "name": "MOCK VERIFIED NAME",
                "dob": "01/01/1990",
                "gender": "M",
                "address": {
                    "house": "1/A",
                    "street": "MG Road",
                    "locality": "Koramangala",
                    "city": "Bengaluru",
                    "state": "Karnataka",
                    "pincode": "560001",
                },
                "verified": True,
                "mock": True,
            },
            evidence=self._build_evidence(aadhaar, True),
        )

    def _build_evidence(self, aadhaar: str, verified: bool) -> EvidenceChain:
        masked = "XXXX-XXXX-" + aadhaar[-4:]
        return EvidenceChain(
            claim=f"aadhaar_verified={masked}",
            supporting=[],
            reconciled_value=str(verified),
            reconciliation_method=ReconciliationMethod.API_AUTHORITATIVE,
            confidence=1.0 if verified else 0.0,
        )
