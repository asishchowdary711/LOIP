"""Aadhaar Secure QR parser and UIDAI RSA-2048 signature verifier.

UIDAI Secure QR binary format:
    payload = zlib_compressed_xml || rsa_signature_256_bytes
    The RSA signature (PKCS1v15 + SHA-256) covers the zlib bytes only.
"""

from __future__ import annotations

import logging
import zlib

from .schemas import AadhaarQRData

logger = logging.getLogger(__name__)

_SIGNATURE_BYTES = 256


class AadhaarQRParser:
    """Parses a raw UIDAI Secure QR binary payload into structured fields.

    Handles both:
    - Secure QR: binary blob (zlib-compressed XML + 256-byte RSA signature)
    - Plain-text QR: older format with just the UID digits
    """

    def parse(self, raw_bytes: bytes) -> tuple[AadhaarQRData, bytes | None]:
        """Decode and parse a UIDAI QR payload.

        Returns (AadhaarQRData, signature_bytes | None).
        signature_bytes is None for plain-text QRs.
        Never raises — returns all-None AadhaarQRData on any failure.
        """
        try:
            if self._is_secure_qr(raw_bytes):
                return self._parse_secure_qr(raw_bytes)
            text = raw_bytes.decode("utf-8", errors="replace")
            return self._parse_plain_text_qr(text), None
        except Exception as exc:
            logger.warning("AadhaarQRParser.parse failed: %s", exc)
            return AadhaarQRData(), None

    def _is_secure_qr(self, raw_bytes: bytes) -> bool:
        if len(raw_bytes) <= _SIGNATURE_BYTES:
            return False
        # The zlib header starts with 0x78; tail 256 bytes contain binary data
        possible_zlib = raw_bytes[:-_SIGNATURE_BYTES]
        return possible_zlib[:2] in (b"\x78\x9c", b"\x78\x01", b"\x78\xda")

    def _parse_secure_qr(self, raw_bytes: bytes) -> tuple[AadhaarQRData, bytes]:
        from loip.validation import parse_aadhaar_xml_qr

        zlib_bytes = raw_bytes[:-_SIGNATURE_BYTES]
        signature_bytes = raw_bytes[-_SIGNATURE_BYTES:]

        xml_bytes = zlib.decompress(zlib_bytes)
        xml_string = xml_bytes.decode("utf-8", errors="replace")

        fields = parse_aadhaar_xml_qr(xml_string)

        address_parts = [
            fields.get("co"), fields.get("house"), fields.get("street"),
            fields.get("lm"), fields.get("loc"), fields.get("vtc"),
            fields.get("dist"), fields.get("state"), fields.get("pc"),
        ]
        address = ", ".join(p for p in address_parts if p)

        # DPDP Act / UIDAI: store only last 4 digits of UID
        raw_uid = fields.get("uid")
        masked_uid = raw_uid[-4:] if raw_uid and len(raw_uid) >= 4 else raw_uid

        data = AadhaarQRData(
            uid=masked_uid,
            full_name=fields.get("name"),
            date_of_birth=fields.get("dob"),
            gender=fields.get("gender"),
            address=address or None,
            mobile_last4=fields.get("phone"),
            email_hash=fields.get("email"),
            raw_xml=xml_string,
        )
        return data, signature_bytes

    def _parse_plain_text_qr(self, text: str) -> AadhaarQRData:
        cleaned = text.strip().replace(" ", "").replace("-", "")
        if cleaned.isdigit() and len(cleaned) == 12:
            return AadhaarQRData(uid=cleaned[-4:])
        return AadhaarQRData()


class AadhaarQRVerifier:
    """Verifies the RSA-2048 PKCS1v15 + SHA-256 signature from UIDAI Secure QR.

    Falls back to signature_valid=False (not a crash) if the key file is
    absent or unparseable — allows the rest of the pipeline to continue.
    """

    def __init__(self, key_path: str | None = None) -> None:
        if key_path is None:
            from loip.config import get_settings
            key_path = get_settings().uidai_public_key_path

        self._public_key = self._load_public_key(key_path)

    def _load_public_key(self, key_path: str):
        try:
            from cryptography.hazmat.primitives.serialization import load_pem_public_key

            with open(key_path, "rb") as f:
                pem_data = f.read()

            if b"PLACEHOLDER" in pem_data or b"BEGIN PUBLIC KEY" not in pem_data:
                logger.warning(
                    "UIDAI public key at %s appears to be a placeholder. "
                    "Obtain the real key from developer.uidai.gov.in.",
                    key_path,
                )
                return None

            return load_pem_public_key(pem_data)
        except FileNotFoundError:
            logger.warning("UIDAI public key not found at %s — signature verification disabled.", key_path)
            return None
        except Exception as exc:
            logger.error("Failed to load UIDAI public key from %s: %s", key_path, exc)
            return None

    def verify_signature(self, payload_bytes: bytes, signature_bytes: bytes) -> bool:
        """Verify RSA-2048 PKCS1v15 + SHA-256 signature.

        payload_bytes: zlib-compressed XML (raw_bytes[:-256])
        signature_bytes: 256-byte RSA signature (raw_bytes[-256:])
        Returns False (never raises) on key-missing or invalid-signature.
        """
        if self._public_key is None:
            return False
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding

            self._public_key.verify(
                signature_bytes,
                payload_bytes,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True
        except Exception:
            return False
