import numpy as np
from loip.domains.document_intel.schemas import OCRResult, OCRBox

class SuryaOCRWrapper:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        
    def extract(self, image: np.ndarray) -> OCRResult:
        if self.mock_mode:
            return OCRResult(
                boxes=[OCRBox(text="MOCK_TEXT_SURYA", confidence=0.90, bbox=(0,0,100,20))],
                mean_confidence=0.90,
                engine="surya",
                raw_text="MOCK_TEXT_SURYA"
            )
        return OCRResult(boxes=[], mean_confidence=0.0, engine="surya", raw_text="")
