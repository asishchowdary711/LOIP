import numpy as np
from loip.domains.document_intel.schemas import ExtractionResult, ExtractionField, DocumentClass

class DonutWrapper:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        
    def extract_structured(self, image: np.ndarray, doc_class: DocumentClass) -> ExtractionResult:
        if self.mock_mode:
            return ExtractionResult(
                document_class=doc_class,
                fields=[ExtractionField(name="fallback_field", value="mock_value", confidence=0.85)],
                model="donut",
                overall_confidence=0.85
            )
        return ExtractionResult(document_class=doc_class, fields=[], model="donut", overall_confidence=0.0)
