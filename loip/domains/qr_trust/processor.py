"""QR Trust Verification orchestrator.

Coordinates QR detection (pyzbar → OpenCV fallback), Aadhaar/PAN parsing,
RSA signature verification, cross-field matching against OCR output, and
tampering analysis into a single QRTrustResult.
"""

from __future__ import annotations

import difflib
import logging
import re

import numpy as np

from .aadhaar_qr import AadhaarQRParser, AadhaarQRVerifier
from .pan_qr import PANQRParser
from .schemas import (
    AadhaarQRData,
    PANQRData,
    QRDataMatch,
    QRDecodeResult,
    QRDocumentType,
    QRTampering,
    QRTrustFlag,
    QRTrustResult,
)
from .tampering import TamperingDetector

logger = logging.getLogger(__name__)

_AADHAAR_DOC_CLASSES = {"aadhaar", "aadhaar_front", "aadhaar_back", "aadhaar_combined"}
_PAN_DOC_CLASSES = {"pan", "pan_card"}


class QRTrustProcessor:
    """Top-level QR trust verification orchestrator.

    mock_mode=True (default) returns deterministic passing results without
    calling pyzbar, OpenCV, or the RSA verifier — matching the pattern used
    by every other LOIP processor.
    """

    def __init__(self, mock_mode: bool = True) -> None:
        self.mock_mode = mock_mode
        self._aadhaar_parser: AadhaarQRParser | None = None
        self._aadhaar_verifier: AadhaarQRVerifier | None = None
        self._pan_parser: PANQRParser | None = None
        self._tampering_detector: TamperingDetector | None = None

        if not mock_mode:
            self._aadhaar_parser = AadhaarQRParser()
            self._aadhaar_verifier = AadhaarQRVerifier()
            self._pan_parser = PANQRParser()
            self._tampering_detector = TamperingDetector(mock_mode=False)

    # ------------------------------------------------------------------
    # Primary public interface
    # ------------------------------------------------------------------

    def verify(
        self,
        application_id: str,
        qr_decode_results: dict[str, QRDecodeResult | None],
        extracted_fields: dict[str, str],
        source_image_bytes: dict[str, bytes] | None = None,
        images_by_class: dict[str, np.ndarray] | None = None,
    ) -> QRTrustResult:
        """Run full QR trust verification.

        qr_decode_results: doc_class → QRDecodeResult | None from DocumentIntelligenceProcessor
        extracted_fields: flat OCR-extracted field dict merged across all documents
        source_image_bytes: raw file bytes per doc_class for EXIF extraction
        images_by_class: numpy arrays per doc_class for ELA
        """
        if self.mock_mode:
            return self._mock_result(application_id)

        from loip.config import get_settings

        settings = get_settings()
        flags: list[QRTrustFlag] = []
        decode_results: list[QRDecodeResult] = []
        aadhaar_qr: AadhaarQRData | None = None
        pan_qr: PANQRData | None = None
        tampering: QRTampering | None = None

        # --- Process each QR result by document class ---
        for doc_class, decode_result in qr_decode_results.items():
            is_aadhaar = doc_class.lower() in _AADHAAR_DOC_CLASSES
            is_pan = doc_class.lower() in _PAN_DOC_CLASSES

            if not (is_aadhaar or is_pan):
                continue

            if decode_result is None:
                flags.append(QRTrustFlag.QR_NOT_FOUND)
                logger.info("No QR found in %s document", doc_class)
                continue

            decode_results.append(decode_result)
            qr_type = self._classify_qr_type(decode_result)
            decode_result.qr_document_type = qr_type

            if is_aadhaar:
                aadhaar_qr = self._process_aadhaar_qr(decode_result, flags)
            elif is_pan:
                pan_qr = self._process_pan_qr(decode_result, flags)

        # --- Tampering analysis (on first Aadhaar or PAN image) ---
        if images_by_class:
            for doc_class, img in images_by_class.items():
                if doc_class.lower() in _AADHAAR_DOC_CLASSES | _PAN_DOC_CLASSES:
                    raw_bytes = (source_image_bytes or {}).get(doc_class)
                    if self._tampering_detector is None:
                        break
                    tampering = self._tampering_detector.analyze(img, raw_bytes)
                    if tampering.ela_anomaly:
                        flags.append(QRTrustFlag.QR_ELA_ANOMALY)
                    if tampering.exif_anomaly:
                        flags.append(QRTrustFlag.QR_EXIF_ANOMALY)
                    if tampering.overall_tampered:
                        flags.append(QRTrustFlag.QR_TAMPERED)
                    break

        # --- Cross-field matching ---
        field_matches = self._cross_check_fields(
            aadhaar_qr, pan_qr, extracted_fields, flags, settings
        )

        trust_score = self._compute_trust_score(aadhaar_qr, pan_qr, field_matches, tampering, flags)

        return QRTrustResult(
            application_id=application_id,
            mock_mode=False,
            aadhaar_qr=aadhaar_qr,
            pan_qr=pan_qr,
            decode_results=decode_results,
            field_matches=field_matches,
            tampering=tampering,
            flags=list(dict.fromkeys(flags)),
            trust_score=trust_score,
        )

    # ------------------------------------------------------------------
    # QR detection (called by DocumentIntelligenceProcessor)
    # ------------------------------------------------------------------

    def detect_and_decode(self, image: np.ndarray) -> QRDecodeResult | None:
        """Detect and decode a QR code from a document image.

        Tries pyzbar first, falls back to cv2.QRCodeDetector.
        Returns None if no QR is found (not an error).
        """
        if self.mock_mode:
            return QRDecodeResult(
                raw_bytes=b"MOCK_QR_PAYLOAD",
                raw_text="MOCK_QR_PAYLOAD",
                decoder_used="mock",
                decode_confidence=0.9,
            )

        result = self._try_pyzbar(image)
        if result is not None:
            return result

        return self._try_opencv(image)

    # ------------------------------------------------------------------
    # Private — classification
    # ------------------------------------------------------------------

    def _classify_qr_type(self, decode_result: QRDecodeResult) -> QRDocumentType:
        raw = decode_result.raw_bytes
        text = decode_result.raw_text or ""

        # Secure QR: binary payload with zlib header
        if len(raw) > 256 and raw[:-256][:2] in (b"\x78\x9c", b"\x78\x01", b"\x78\xda"):
            return QRDocumentType.AADHAAR_SECURE_QR

        # PAN QR: matches PAN pattern or Base64 of pipe-delimited PAN record
        import re
        pan_pattern = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
        if pan_pattern.match(text.strip()):
            return QRDocumentType.PAN_QR
        try:
            import base64
            decoded = base64.b64decode(text.strip(), validate=True).decode("utf-8")
            if "|" in decoded and pan_pattern.match(decoded.split("|")[0].strip()):
                return QRDocumentType.PAN_QR
        except Exception:
            pass

        # Plain-text Aadhaar UID
        stripped = text.strip().replace(" ", "").replace("-", "")
        if stripped.isdigit() and len(stripped) == 12:
            return QRDocumentType.AADHAAR_TEXT_QR

        return QRDocumentType.UNKNOWN

    # ------------------------------------------------------------------
    # Private — Aadhaar processing
    # ------------------------------------------------------------------

    def _process_aadhaar_qr(
        self,
        decode_result: QRDecodeResult,
        flags: list[QRTrustFlag],
    ) -> AadhaarQRData:
        if self._aadhaar_parser is None or self._aadhaar_verifier is None:
            flags.append(QRTrustFlag.QR_DECODE_FAILED)
            return AadhaarQRData()

        data, signature_bytes = self._aadhaar_parser.parse(decode_result.raw_bytes)

        if signature_bytes is None:
            flags.append(QRTrustFlag.QR_SIGNATURE_MISSING)
            data.signature_valid = False
        else:
            zlib_bytes = decode_result.raw_bytes[:-256]
            valid = self._aadhaar_verifier.verify_signature(zlib_bytes, signature_bytes)
            data.signature_valid = valid
            if not valid:
                flags.append(QRTrustFlag.QR_SIGNATURE_INVALID)

        return data

    # ------------------------------------------------------------------
    # Private — PAN processing
    # ------------------------------------------------------------------

    def _process_pan_qr(
        self,
        decode_result: QRDecodeResult,
        flags: list[QRTrustFlag],
    ) -> PANQRData:
        if self._pan_parser is None:
            flags.append(QRTrustFlag.QR_DECODE_FAILED)
            return PANQRData()

        text = decode_result.raw_text or decode_result.raw_bytes.decode("utf-8", errors="replace")
        data = self._pan_parser.parse(text)

        if not data.format_valid:
            flags.append(QRTrustFlag.QR_DECODE_FAILED)

        return data

    # ------------------------------------------------------------------
    # Private — cross-field comparison
    # ------------------------------------------------------------------

    def _cross_check_fields(
        self,
        aadhaar_qr: AadhaarQRData | None,
        pan_qr: PANQRData | None,
        extracted_fields: dict[str, str],
        flags: list[QRTrustFlag],
        settings,
    ) -> list[QRDataMatch]:
        matches: list[QRDataMatch] = []
        name_thresh = settings.qr_name_similarity_threshold
        addr_thresh = settings.qr_address_similarity_threshold

        def _sim(a: str | None, b: str | None) -> float:
            if not a or not b:
                return 0.0
            return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()

        def _exact(a: str | None, b: str | None) -> float:
            if a and b:
                a_clean = re.sub(r"[\s\-/]", "", a).lower()
                b_clean = re.sub(r"[\s\-/]", "", b).lower()
                return 1.0 if a_clean == b_clean else 0.0
            return 0.0

        # Name — only cross-check if we actually decoded a QR with a name.
        # An absent QR is already captured by QR_NOT_FOUND; treating it as a
        # mismatch would double-penalise the applicant.
        qr_name = (aadhaar_qr.full_name if aadhaar_qr else None) or (pan_qr.full_name if pan_qr else None)
        ocr_name = extracted_fields.get("full_name")
        if qr_name:
            score = _sim(qr_name, ocr_name)
            passed = score >= name_thresh
            matches.append(QRDataMatch(
                field_name="full_name", qr_value=qr_name, ocr_value=ocr_name,
                similarity_score=score, threshold=name_thresh, passed=passed,
            ))
            if not passed:
                flags.append(QRTrustFlag.QR_NAME_MISMATCH)

        # DOB — same rule: skip when no QR was decoded.
        qr_dob = (aadhaar_qr.date_of_birth if aadhaar_qr else None) or (pan_qr.date_of_birth if pan_qr else None)
        ocr_dob = extracted_fields.get("date_of_birth")
        if qr_dob:
            score = _exact(qr_dob, ocr_dob)
            passed = score == 1.0
            matches.append(QRDataMatch(
                field_name="date_of_birth", qr_value=qr_dob, ocr_value=ocr_dob,
                similarity_score=score, threshold=1.0, passed=passed,
            ))
            if not passed:
                flags.append(QRTrustFlag.QR_DOB_MISMATCH)

        # Address (Aadhaar only)
        if aadhaar_qr and aadhaar_qr.address:
            ocr_addr = extracted_fields.get("address")
            score = _sim(aadhaar_qr.address, ocr_addr)
            passed = score >= addr_thresh
            matches.append(QRDataMatch(
                field_name="address", qr_value=aadhaar_qr.address, ocr_value=ocr_addr,
                similarity_score=score, threshold=addr_thresh, passed=passed,
            ))
            if not passed:
                flags.append(QRTrustFlag.QR_ADDRESS_MISMATCH)

        # Aadhaar UID last-4
        if aadhaar_qr and aadhaar_qr.uid:
            ocr_uid = extracted_fields.get("aadhaar_number", "")
            qr_last4 = aadhaar_qr.uid[-4:] if len(aadhaar_qr.uid) >= 4 else aadhaar_qr.uid
            ocr_last4 = ocr_uid.replace(" ", "").replace("-", "")[-4:] if ocr_uid else ""
            passed = bool(qr_last4 and ocr_last4 and qr_last4 == ocr_last4)
            matches.append(QRDataMatch(
                field_name="aadhaar_last4", qr_value=qr_last4, ocr_value=ocr_last4,
                similarity_score=1.0 if passed else 0.0, threshold=1.0, passed=passed,
            ))
            if not passed and ocr_uid:
                flags.append(QRTrustFlag.QR_ID_NUMBER_MISMATCH)

        # PAN number
        if pan_qr and pan_qr.pan_number:
            ocr_pan = extracted_fields.get("pan_number")
            score = _exact(pan_qr.pan_number, ocr_pan)
            passed = score == 1.0
            matches.append(QRDataMatch(
                field_name="pan_number", qr_value=pan_qr.pan_number, ocr_value=ocr_pan,
                similarity_score=score, threshold=1.0, passed=passed,
            ))
            if not passed and ocr_pan:
                flags.append(QRTrustFlag.QR_ID_NUMBER_MISMATCH)

        return matches

    # ------------------------------------------------------------------
    # Private — trust scoring
    # ------------------------------------------------------------------

    def _compute_trust_score(
        self,
        aadhaar_qr: AadhaarQRData | None,
        pan_qr: PANQRData | None,
        field_matches: list[QRDataMatch],
        tampering: QRTampering | None,
        flags: list[QRTrustFlag],
    ) -> float:
        deduction = 0.0

        if QRTrustFlag.QR_NOT_FOUND in flags:
            deduction += 0.20
        if QRTrustFlag.QR_DECODE_FAILED in flags:
            deduction += 0.20
        if QRTrustFlag.QR_SIGNATURE_INVALID in flags:
            deduction += 0.35
        elif QRTrustFlag.QR_SIGNATURE_MISSING in flags:
            deduction += 0.10

        for match in field_matches:
            if not match.passed:
                deduction += 0.10

        if tampering is not None:
            if tampering.overall_tampered:
                deduction += 0.30
            else:
                if tampering.ela_anomaly:
                    deduction += 0.10
                if tampering.exif_anomaly:
                    deduction += 0.10

        return max(0.0, 1.0 - deduction)

    # ------------------------------------------------------------------
    # Private — mock result
    # ------------------------------------------------------------------

    def _mock_result(self, application_id: str) -> QRTrustResult:
        return QRTrustResult(
            application_id=application_id,
            mock_mode=True,
            aadhaar_qr=AadhaarQRData(
                uid="1234",
                full_name="MOCK APPLICANT",
                date_of_birth="01/01/1990",
                gender="M",
                address="123 Mock Street, Mock City, Mock State 000000",
                signature_valid=True,
            ),
            pan_qr=PANQRData(
                pan_number="ABCDE1234F",
                full_name="MOCK APPLICANT",
                date_of_birth="01/01/1990",
                father_name="MOCK FATHER",
                format_valid=True,
            ),
            decode_results=[
                QRDecodeResult(
                    raw_bytes=b"MOCK_QR_PAYLOAD",
                    raw_text="MOCK_QR_PAYLOAD",
                    qr_document_type=QRDocumentType.AADHAAR_SECURE_QR,
                    decoder_used="mock",
                    decode_confidence=0.9,
                )
            ],
            field_matches=[
                QRDataMatch(
                    field_name="full_name",
                    qr_value="MOCK APPLICANT",
                    ocr_value="MOCK APPLICANT",
                    similarity_score=1.0,
                    threshold=0.80,
                    passed=True,
                ),
                QRDataMatch(
                    field_name="date_of_birth",
                    qr_value="01/01/1990",
                    ocr_value="01/01/1990",
                    similarity_score=1.0,
                    threshold=1.0,
                    passed=True,
                ),
            ],
            tampering=QRTampering(
                ela_score=0.04,
                ela_anomaly=False,
                ela_threshold=0.15,
                exif_anomalies=[],
                exif_anomaly=False,
                overall_tampered=False,
            ),
            flags=[],
            trust_score=0.9,
        )

    # ------------------------------------------------------------------
    # Private — decoders
    # ------------------------------------------------------------------

    def _try_pyzbar(self, image: np.ndarray) -> QRDecodeResult | None:
        try:
            from pyzbar.pyzbar import decode as pyzbar_decode

            symbols = pyzbar_decode(image)
            if not symbols:
                return None
            sym = symbols[0]
            raw = sym.data
            rect = sym.rect
            bbox = (rect.left, rect.top, rect.left + rect.width, rect.top + rect.height)
            try:
                text: str | None = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = None
            return QRDecodeResult(
                raw_bytes=raw,
                raw_text=text,
                decoder_used="pyzbar",
                decode_confidence=1.0,
                bounding_box=bbox,
            )
        except ImportError:
            logger.debug("pyzbar not installed, falling back to OpenCV QRCodeDetector")
            return None
        except Exception as exc:
            logger.debug("pyzbar decode failed: %s", exc)
            return None

    def _try_opencv(self, image: np.ndarray) -> QRDecodeResult | None:
        try:
            import cv2

            detector = cv2.QRCodeDetector()
            data, points, _ = detector.detectAndDecode(image)
            if not data or points is None:
                return None
            raw = data.encode("utf-8")
            return QRDecodeResult(
                raw_bytes=raw,
                raw_text=data,
                decoder_used="opencv",
                decode_confidence=0.85,
            )
        except Exception as exc:
            logger.debug("OpenCV QR decode failed: %s", exc)
            return None
