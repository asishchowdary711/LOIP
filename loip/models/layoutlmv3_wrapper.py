import numpy as np
from loip.domains.document_intel.schemas import ClassificationResult, DocumentClass

class LayoutLMv3Wrapper:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        
    def classify(self, image: np.ndarray) -> ClassificationResult:
        if self.mock_mode:
            h = image.shape[0]
            if h == 100: doc_class = DocumentClass.PAN
            elif h == 101: doc_class = DocumentClass.AADHAAR
            elif h == 102: doc_class = DocumentClass.SALARY_SLIP
            else: doc_class = DocumentClass.SALARY_SLIP
            
            return ClassificationResult(
                document_class=doc_class,
                confidence=0.98,
                needs_review=False,
                logits={doc_class.value: 0.98, "other": 0.01}
            )
        return ClassificationResult(document_class=DocumentClass.REJECT, confidence=0.0)
