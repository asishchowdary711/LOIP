import numpy as np

from loip.models.paddleocr_wrapper import PaddleOCRWrapper
from loip.models.surya_wrapper import SuryaOCRWrapper
from loip.models.layoutlmv3_wrapper import LayoutLMv3Wrapper
from loip.models.qwen2_5_vl_wrapper import Qwen25VLWrapper
from loip.models.donut_wrapper import DonutWrapper

from .schemas import (
    DocumentClass, ClassificationResult, OCRResult, OCRConflict, 
    ExtractionResult, CLASSIFICATION_CONFIDENCE_THRESHOLD,
    OCR_FALLBACK_THRESHOLD, OCR_CONFLICT_THRESHOLD, EXTRACTION_FALLBACK_THRESHOLD
)

class DocumentIntelligenceProcessor:
    def __init__(self, mock_mode: bool = True):
        self.classifier = LayoutLMv3Wrapper(mock_mode=mock_mode)
        self.primary_ocr = PaddleOCRWrapper(mock_mode=mock_mode)
        self.secondary_ocr = SuryaOCRWrapper(mock_mode=mock_mode)
        self.primary_extractor = Qwen25VLWrapper(mock_mode=mock_mode)
        self.secondary_extractor = DonutWrapper(mock_mode=mock_mode)

    def classify_document(self, image: np.ndarray) -> ClassificationResult:
        result = self.classifier.classify(image)
        if result.confidence < CLASSIFICATION_CONFIDENCE_THRESHOLD:
            result.needs_review = True
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

    def extract_fields(self, image: np.ndarray, doc_class: DocumentClass) -> ExtractionResult:
        primary_result = self.primary_extractor.extract_fields(image, doc_class)
        
        if primary_result.overall_confidence >= EXTRACTION_FALLBACK_THRESHOLD:
            return primary_result
            
        secondary_result = self.secondary_extractor.extract_structured(image, doc_class)
        return primary_result if primary_result.overall_confidence > secondary_result.overall_confidence else secondary_result

    def process(self, image: np.ndarray) -> dict:
        """End-to-end document processing pipeline."""
        classification = self.classify_document(image)
        ocr = self.perform_ocr(image)
        extraction = self.extract_fields(image, classification.document_class)
        
        return {
            "classification": classification,
            "ocr": ocr,
            "extraction": extraction
        }
