"""Unit tests for Aadhaar (Verhoeff) and passport MRZ (ICAO 9303) checksums.

Pure/deterministic — no infrastructure required.
"""

from loip.validation import (
    is_valid_aadhaar,
    mrz_check_digit,
    validate_mrz_td3,
    verhoeff_checksum_valid,
)

# Canonical ICAO 9303 TD3 sample (line 2).
ICAO_MRZ_LINE2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"
VALID_AADHAAR = "234123412346"  # Verhoeff-valid, starts with 2


def test_verhoeff_accepts_valid_and_rejects_tampered():
    assert verhoeff_checksum_valid("2363")
    assert not verhoeff_checksum_valid("2364")


def test_is_valid_aadhaar():
    assert is_valid_aadhaar(VALID_AADHAAR)
    assert is_valid_aadhaar("2341 2341 2346")  # spaces tolerated
    # last digit tampered -> checksum fails
    assert not is_valid_aadhaar(VALID_AADHAAR[:-1] + ("0" if VALID_AADHAAR[-1] != "0" else "5"))
    assert not is_valid_aadhaar("12345")            # wrong length
    assert not is_valid_aadhaar("123456789012")     # starts with 1 (invalid) + bad checksum


def test_mrz_check_digit():
    # From the canonical TD3 line: dob "740812" has check digit "2".
    assert mrz_check_digit("740812") == "2"
    # passport number "L898902C3" has check digit "6".
    assert mrz_check_digit("L898902C3") == "6"


def test_validate_mrz_td3():
    assert validate_mrz_td3(ICAO_MRZ_LINE2)
    # corrupt the composite check digit
    assert not validate_mrz_td3(ICAO_MRZ_LINE2[:-1] + "9")
    assert not validate_mrz_td3("too-short")
