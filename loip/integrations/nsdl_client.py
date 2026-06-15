"""NSDL / UTI PAN verification API client.

Verifies PAN number against NSDL database. Returns name match status,
PAN active/inactive status, and name on record.

Used in Phase 1b identity verification. API-authoritative results
override document-extracted values via reconciliation_method="api_authoritative".
"""

from __future__ import annotations

import re
from datetime import datetime

from loip.schemas.evidence import (
    EvidenceChain,
    ExtractionMethod,
    ReconciliationMethod,
    SourceLocation,
)
from loip.schemas.identity import APIVerificationResult

from .base import BaseClient, IntegrationError

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


class NSDLClient(BaseClient):
    service_name = "nsdl"
    env_prefix = "NSDL"

    async def verify_pan(
        self,
        pan_number: str,
        full_name: str,
        dob: str,
    ) -> APIVerificationResult:
        """Verify PAN number against NSDL database.

        Args:
            pan_number: PAN in format ABCDE1234F
            full_name: Name to match against NSDL records
            dob: Date of birth in DD/MM/YYYY format
        """
        if not PAN_REGEX.match(pan_number):
            return APIVerificationResult(
                source="nsdl_api",
                matched=False,
                status="format_invalid",
                evidence=self._build_evidence(pan_number),
            )

        if self._mock:
            return self._mock_response(pan_number, full_name)

        try:
            data = await self._request("POST", "", json_body={
                "pan": pan_number,
                "name": full_name,
                "dob": dob,
            })
        except IntegrationError:
            raise

        return APIVerificationResult(
            source="nsdl_api",
            matched=data.get("name_match", False),
            status=data.get("status", "unknown"),
            raw_response=data,
            evidence=self._build_evidence(pan_number),
        )

    def _mock_response(self, pan: str, name: str) -> APIVerificationResult:
        return APIVerificationResult(
            source="nsdl_api",
            matched=True,
            status="active",
            raw_response={
                "pan": pan,
                "name_on_pan": name.upper(),
                "name_match": True,
                "status": "active",
                "mock": True,
            },
            evidence=self._build_evidence(pan),
        )

    def _build_evidence(self, pan: str) -> EvidenceChain:
        return EvidenceChain(
            claim=f"pan_verified={pan}",
            supporting=[],
            reconciled_value=pan,
            reconciliation_method=ReconciliationMethod.API_AUTHORITATIVE,
            confidence=1.0,
        )
