"""PAN card QR parser for Income Tax Department QR codes.

Post-2017 PAN QR format:
    Base64-encoded string decoding to pipe-delimited fields:
    <PAN>|<Full Name>|<Father Name>|<DOB DD/MM/YYYY>

Older PAN cards may carry only the alphanumeric PAN number as plain text.
"""

from __future__ import annotations

import base64
import logging
import re

from .schemas import PANQRData

logger = logging.getLogger(__name__)

_PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


class PANQRParser:
    """Parses and validates an Income Tax Department PAN QR code payload."""

    def parse(self, raw_text: str) -> PANQRData:
        """Decode and parse a PAN QR payload.

        Returns PANQRData with format_valid=True when PAN passes regex.
        Never raises.
        """
        try:
            raw_text = raw_text.strip()

            # Try Base64-encoded pipe-delimited format first
            decoded = self._try_base64_decode(raw_text)
            if decoded and "|" in decoded:
                return self._parse_pipe_delimited(decoded)

            # Fallback: plain PAN text QR
            if _PAN_PATTERN.match(raw_text):
                return PANQRData(pan_number=raw_text, format_valid=True)

            return PANQRData(format_valid=False)
        except Exception as exc:
            logger.warning("PANQRParser.parse failed: %s", exc)
            return PANQRData(format_valid=False)

    def _try_base64_decode(self, raw_text: str) -> str | None:
        try:
            decoded_bytes = base64.b64decode(raw_text, validate=True)
            return decoded_bytes.decode("utf-8")
        except Exception:
            return None

    def _parse_pipe_delimited(self, decoded: str) -> PANQRData:
        parts = decoded.split("|")
        pan = parts[0].strip().upper() if len(parts) > 0 else None
        name = parts[1].strip() if len(parts) > 1 else None
        father_name = parts[2].strip() if len(parts) > 2 else None
        dob = parts[3].strip() if len(parts) > 3 else None

        format_valid = bool(pan and _PAN_PATTERN.match(pan))
        return PANQRData(
            pan_number=pan,
            full_name=name,
            date_of_birth=dob,
            father_name=father_name,
            format_valid=format_valid,
        )
