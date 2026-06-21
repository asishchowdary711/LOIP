import base64
import json
import logging
import re
import urllib.request

import numpy as np

from loip.models.paddleocr_wrapper import PaddleOCRWrapper
from loip.models.surya_wrapper import SuryaOCRWrapper
from loip.models.layoutlmv3_wrapper import LayoutLMv3Wrapper
from loip.models.qwen2_5_vl_wrapper import Qwen25VLWrapper, OLLAMA_HOST, OLLAMA_MODEL
from loip.models.donut_wrapper import DonutWrapper

from .schemas import (
    DocumentClass, ClassificationResult, OCRResult, OCRConflict,
    ExtractionResult, CLASSIFICATION_CONFIDENCE_THRESHOLD,
    OCR_FALLBACK_THRESHOLD, OCR_CONFLICT_THRESHOLD, EXTRACTION_FALLBACK_THRESHOLD
)

_QR_ELIGIBLE_CLASSES = {DocumentClass.PAN, DocumentClass.AADHAAR}

logger = logging.getLogger(__name__)

_DOC_CLASS_NAMES = {
    "pan": DocumentClass.PAN,
    "aadhaar": DocumentClass.AADHAAR,
    "salary_slip": DocumentClass.SALARY_SLIP,
    "bank_statement": DocumentClass.BANK_STATEMENT,
    "form16": DocumentClass.FORM16,
    "itr": DocumentClass.ITR,
    "gst_return": DocumentClass.GST_RETURN,
    "passport": DocumentClass.PASSPORT,
    "driving_licence": DocumentClass.DRIVING_LICENCE,
}


class DocumentIntelligenceProcessor:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self.classifier = LayoutLMv3Wrapper(mock_mode=mock_mode)
        self.primary_ocr = PaddleOCRWrapper(mock_mode=mock_mode)
        self.secondary_ocr = SuryaOCRWrapper(mock_mode=mock_mode)
        self.primary_extractor = Qwen25VLWrapper(mock_mode=mock_mode)
        self.secondary_extractor = DonutWrapper(mock_mode=mock_mode)
        # QRTrustProcessor is imported lazily to avoid circular imports
        self._qr_processor = None

    def _classify_via_ollama(self, image: np.ndarray) -> ClassificationResult | None:
        """Ask Qwen2.5-VL via Ollama to classify the document type.
        Returns None if Ollama is unreachable or returns an unrecognised type."""
        import time
        import urllib.error
        from loip.models.qwen2_5_vl_wrapper import _OLLAMA_SEMAPHORE, _prepare_image

        img_bytes, _ = _prepare_image(image)
        if not img_bytes:
            return None
        img_b64 = base64.b64encode(img_bytes).decode()

        valid_types = ", ".join(_DOC_CLASS_NAMES.keys())
        prompt = (
            f"What type of Indian financial/identity document is this? "
            f"Reply with ONLY one of these exact values: {valid_types}. "
            f"No other text."
        )
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "keep_alive": "10m",
            "options": {"temperature": 0, "num_ctx": 1024, "num_predict": 32},
        }
        body = None
        backoff = 1.0
        with _OLLAMA_SEMAPHORE:
            for attempt in range(3):
                req = urllib.request.Request(
                    f"{OLLAMA_HOST}/api/generate",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                try:
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        body = json.loads(resp.read())
                    break
                except urllib.error.HTTPError as exc:
                    if 500 <= exc.code < 600 and attempt < 2:
                        logger.warning("Ollama classify HTTP %d (attempt %d/3) — retrying in %.1fs",
                                       exc.code, attempt + 1, backoff)
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                    logger.warning("Ollama classification request failed: %s", exc)
                    return None
                except (OSError, ValueError) as exc:
                    logger.warning("Ollama classification request failed: %s", exc)
                    return None

        if body is None:
            return None

        raw = body.get("response", "").strip().lower().replace(" ", "_")
        doc_class = _DOC_CLASS_NAMES.get(raw)
        if doc_class is None:
            # Try partial match
            for key, cls in _DOC_CLASS_NAMES.items():
                if key in raw:
                    doc_class = cls
                    break
        if doc_class is None:
            logger.warning("Ollama returned unrecognised doc type: %r", raw)
            return None

        logger.info("Ollama classified document as: %s", doc_class)
        return ClassificationResult(
            document_class=doc_class,
            confidence=0.88,
            needs_review=False,
            logits={doc_class.value: 0.88},
        )

    def classify_document(self, image: np.ndarray) -> ClassificationResult:
        result = self.classifier.classify(image)
        is_classifier_mocked = getattr(self.classifier, "mock_mode", True)
        is_ocr_mocked = False
        if hasattr(self.classifier, "_ocr") and self.classifier._ocr is not None:
            is_ocr_mocked = self.classifier._ocr.mock_mode

        if is_classifier_mocked or is_ocr_mocked or result.confidence < CLASSIFICATION_CONFIDENCE_THRESHOLD:
            result.needs_review = True
            # When LayoutLMv3 confidence is low (e.g. OCR unavailable), try
            # asking the vision LLM directly — it sees the image and can
            # identify document type without needing OCR bounding boxes.
            if not self.mock_mode:
                fallback = self._classify_via_ollama(image)
                if fallback is not None:
                    return fallback
        return result

    def perform_ocr(self, image: np.ndarray) -> OCRResult | OCRConflict:
        primary_result = self.primary_ocr.extract(image)

        if primary_result.mean_confidence >= OCR_FALLBACK_THRESHOLD:
            return primary_result

        secondary_result = self.secondary_ocr.extract(image)

        if abs(primary_result.mean_confidence - secondary_result.mean_confidence) > OCR_CONFLICT_THRESHOLD:
            return OCRConflict(
                primary=primary_result,
                secondary=secondary_result,
                confidence_delta=abs(primary_result.mean_confidence - secondary_result.mean_confidence)
            )

        return primary_result if primary_result.mean_confidence > secondary_result.mean_confidence else secondary_result

    def _detect_qr(self, image: np.ndarray, doc_class: DocumentClass):
        """Detect and decode a QR code if the document class is QR-eligible.

        Returns QRDecodeResult or None. None means either the doc class is
        not expected to carry a QR, or no QR was found — both are normal.
        """
        if doc_class not in _QR_ELIGIBLE_CLASSES:
            return None

        if self._qr_processor is None:
            from loip.domains.qr_trust.processor import QRTrustProcessor
            self._qr_processor = QRTrustProcessor(mock_mode=self.mock_mode)

        return self._qr_processor.detect_and_decode(image)

    def extract_fields(self, image: np.ndarray, doc_class: DocumentClass) -> ExtractionResult:
        primary_result = self.primary_extractor.extract_fields(image, doc_class)

        if primary_result.overall_confidence >= EXTRACTION_FALLBACK_THRESHOLD:
            return primary_result

        secondary_result = self.secondary_extractor.extract_structured(image, doc_class)
        return primary_result if primary_result.overall_confidence > secondary_result.overall_confidence else secondary_result

    @staticmethod
    def _patch_aadhaar_from_ocr(extraction: "ExtractionResult", ocr) -> "ExtractionResult":
        """If the VL model missed aadhaar_number, try to find a 12-digit
        sequence in the raw OCR text (PaddleOCR/Surya always reads the number
        even when the VL model doesn't label it)."""
        from .schemas import ExtractionField

        has_aadhaar = any(f.name == "aadhaar_number" and f.value for f in extraction.fields)
        if has_aadhaar:
            return extraction

        raw_text = ""
        if ocr is not None:
            raw_text = getattr(ocr, "raw_text", "") or ""
            if not raw_text:
                for attr in ("primary", "secondary"):
                    sub = getattr(ocr, attr, None)
                    if sub is not None:
                        raw_text += " " + (getattr(sub, "raw_text", "") or "")

        digits_only = re.sub(r"\D", "", raw_text)
        match = re.search(r"\d{12}", digits_only)
        if match:
            aadhaar_num = match.group()
            logger.info("Patched aadhaar_number from OCR text: %s", aadhaar_num)
            extraction.fields.append(
                ExtractionField(name="aadhaar_number", value=aadhaar_num, confidence=0.75)
            )
        return extraction

    def process(self, image: np.ndarray) -> dict:
        """End-to-end document processing pipeline."""
        import hashlib
        try:
            h = hashlib.md5(image).hexdigest()
        except Exception:
            h = str(id(image))

        if not hasattr(self, "_cache"):
            self._cache = {}

        if h in self._cache:
            logger.info("Returning cached document intelligence result for image hash %s", h)
            return self._cache[h]

        classification = self.classify_document(image)
        ocr = self.perform_ocr(image)
        extraction = self.extract_fields(image, classification.document_class)

        if classification.document_class == DocumentClass.AADHAAR:
            extraction = self._patch_aadhaar_from_ocr(extraction, ocr)

        qr = self._detect_qr(image, classification.document_class)

        result = {
            "classification": classification,
            "ocr": ocr,
            "extraction": extraction,
            "qr": qr,
        }
        self._cache[h] = result
        return result
