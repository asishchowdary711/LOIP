"""DigiLocker API client for government-issued document fetch.

DigiLocker provides digitally signed copies of government documents
(PAN, Aadhaar, driving licence, etc.) via the borrower's consent.
Documents fetched from DigiLocker are considered tamper-proof
(digitally signed by issuing authority).
"""

from __future__ import annotations

from dataclasses import dataclass

from loip.schemas.evidence import (
    EvidenceChain,
    ReconciliationMethod,
)

from .base import BaseClient, ConsentRequiredError, IntegrationError


@dataclass
class DigiLockerDocument:
    doc_type: str
    issuer: str
    uri: str
    content_type: str
    raw_bytes: bytes | None
    digital_signature_valid: bool
    metadata: dict


class DigiLockerClient(BaseClient):
    service_name = "digilocker"
    env_prefix = "DIGILOCKER"

    async def fetch_document(
        self,
        doc_type: str,
        identifier: str,
        consent_verified: bool = False,
    ) -> DigiLockerDocument:
        """Fetch a document from DigiLocker.

        Args:
            doc_type: Document type code (e.g. "PANCR" for PAN, "ADHAR" for Aadhaar)
            identifier: Document identifier (PAN number, Aadhaar number, etc.)
            consent_verified: Caller must set True after confirming consent exists
        """
        if not consent_verified:
            raise ConsentRequiredError("digilocker", "document_processing")

        if self._mock:
            return self._mock_response(doc_type, identifier)

        try:
            data = await self._request("POST", "fetch", json_body={
                "doc_type": doc_type,
                "identifier": identifier,
            })
        except IntegrationError:
            raise

        return DigiLockerDocument(
            doc_type=doc_type,
            issuer=data.get("issuer", ""),
            uri=data.get("uri", ""),
            content_type=data.get("content_type", "application/pdf"),
            raw_bytes=None,
            digital_signature_valid=data.get("signature_valid", False),
            metadata=data.get("metadata", {}),
        )

    async def list_issued_documents(self, consent_verified: bool = False) -> list[dict]:
        """List all documents available in borrower's DigiLocker."""
        if not consent_verified:
            raise ConsentRequiredError("digilocker", "document_processing")

        if self._mock:
            return [
                {"doc_type": "PANCR", "issuer": "NSDL", "name": "PAN Card"},
                {"doc_type": "ADHAR", "issuer": "UIDAI", "name": "Aadhaar"},
                {"doc_type": "DRVLC", "issuer": "MoRTH", "name": "Driving Licence"},
            ]

        data = await self._request("GET", "documents/issued")
        return data.get("documents", [])

    def _mock_response(self, doc_type: str, identifier: str) -> DigiLockerDocument:
        issuers = {
            "PANCR": "NSDL",
            "ADHAR": "UIDAI",
            "DRVLC": "MoRTH",
            "ITRNS": "Income Tax Department",
        }
        return DigiLockerDocument(
            doc_type=doc_type,
            issuer=issuers.get(doc_type, "Government of India"),
            uri=f"digilocker://{doc_type}/{identifier}",
            content_type="application/pdf",
            raw_bytes=None,
            digital_signature_valid=True,
            metadata={
                "identifier": identifier,
                "doc_type": doc_type,
                "mock": True,
            },
        )
