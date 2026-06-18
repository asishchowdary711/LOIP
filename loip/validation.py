"""Deterministic document-number validation — Aadhaar (Verhoeff), passport
MRZ (ICAO Doc 9303) check digits, and QR payload parsing helpers.

These are real, model-free checks: they run on extracted/entered values
regardless of whether the OCR/VLM extraction is mock or real, and back the
build-plan rules ``aadhaar_format_invalid`` (Verhoeff) and ``MRZ checksum
fail``.
"""

from __future__ import annotations

import re

try:
    from defusedxml.ElementTree import fromstring as _xml_fromstring
    from defusedxml.ElementTree import ParseError as _XMLParseError
except ImportError:
    # defusedxml not installed — fall back to stdlib with a warning.
    # Only affects environments that haven't run: pip install defusedxml
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "defusedxml not installed; XML parsing of Aadhaar QR payloads uses stdlib "
        "xml.etree.ElementTree which is vulnerable to entity expansion DoS. "
        "Install defusedxml for production use."
    )
    from xml.etree.ElementTree import fromstring as _xml_fromstring  # noqa: S405
    from xml.etree.ElementTree import ParseError as _XMLParseError

# --- Verhoeff (Aadhaar) ----------------------------------------------------

# Multiplication table (dihedral group D5).
_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
# Permutation table.
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_checksum_valid(number: str) -> bool:
    """True if ``number`` (digits only) passes the Verhoeff checksum."""
    digits = [int(c) for c in reversed(number)]
    check = 0
    for i, d in enumerate(digits):
        check = _VERHOEFF_D[check][_VERHOEFF_P[i % 8][d]]
    return check == 0


def is_valid_aadhaar(aadhaar: str) -> bool:
    """12 digits, not starting with 0/1 (UIDAI rule), and Verhoeff-valid."""
    cleaned = aadhaar.replace(" ", "").replace("-", "")
    if len(cleaned) != 12 or not cleaned.isdigit():
        return False
    if cleaned[0] in "01":
        return False
    return verhoeff_checksum_valid(cleaned)


# --- MRZ (passport TD3, ICAO Doc 9303) -------------------------------------

_MRZ_WEIGHTS = [7, 3, 1]


def _mrz_char_value(ch: str) -> int:
    if ch == "<":
        return 0
    if ch.isdigit():
        return int(ch)
    if ch.isalpha():
        return ord(ch.upper()) - ord("A") + 10
    raise ValueError(f"invalid MRZ character: {ch!r}")


def mrz_check_digit(data: str) -> str:
    """ICAO 9303 check digit for an MRZ field."""
    total = sum(_mrz_char_value(ch) * _MRZ_WEIGHTS[i % 3] for i, ch in enumerate(data))
    return str(total % 10)


def validate_mrz_td3(line2: str) -> bool:
    """Validate the composite check digit of a TD3 (passport) MRZ second line.

    ``line2`` is the 44-char second MRZ line:
    passport_no(9) cd(1) nationality(3) dob(6) cd(1) sex(1) expiry(6) cd(1)
    personal_no(14) cd(1) composite_cd(1).
    """
    line = line2.replace(" ", "")
    if len(line) != 44:
        return False
    try:
        passport_no, passport_cd = line[0:9], line[9]
        dob, dob_cd = line[13:19], line[19]
        expiry, expiry_cd = line[21:27], line[27]
        personal, personal_cd = line[28:42], line[42]
        composite_cd = line[43]

        if mrz_check_digit(passport_no) != passport_cd:
            return False
        if mrz_check_digit(dob) != dob_cd:
            return False
        if mrz_check_digit(expiry) != expiry_cd:
            return False
        if mrz_check_digit(personal) != personal_cd:
            return False
        composite = passport_no + passport_cd + dob + dob_cd + expiry + expiry_cd + personal + personal_cd
        return mrz_check_digit(composite) == composite_cd
    except (ValueError, IndexError):
        return False


# --- QR payload parsing helpers --------------------------------------------

_PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")

_AADHAAR_XML_FIELD_MAP = {
    "uid": "uid",
    "name": "name",
    "dob": "dob",
    "gender": "gender",
    "co": "co",
    "house": "house",
    "street": "street",
    "lm": "lm",
    "loc": "loc",
    "vtc": "vtc",
    "dist": "dist",
    "state": "state",
    "pc": "pc",
    "phone": "phone",
    "email": "email",
}


def parse_aadhaar_xml_qr(xml_string: str) -> dict[str, str | None]:
    """Parse a UIDAI Aadhaar Secure QR XML string into a flat field dict.

    The expected root element is ``<PrintLetterBarcodeData>``. All fields
    are returned as strings or None. No UIDAI API call is made.

    On XML parse failure returns a dict with all values as None.
    """
    result: dict[str, str | None] = {k: None for k in _AADHAAR_XML_FIELD_MAP}
    try:
        root = _xml_fromstring(xml_string)
        for attr_name, field_key in _AADHAAR_XML_FIELD_MAP.items():
            result[field_key] = root.get(attr_name)
    except _XMLParseError:
        pass
    return result


def validate_pan_qr_format(pan_number: str) -> bool:
    """Validate a PAN number against the Income Tax Department format.

    Format: [A-Z]{5}[0-9]{4}[A-Z] (10 chars, uppercase).
    Whitespace is stripped before matching. No NSDL API call is made.
    """
    return bool(_PAN_PATTERN.match(pan_number.strip()))
