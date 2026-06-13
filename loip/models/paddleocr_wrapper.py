import numpy as np
from loip.domains.document_intel.schemas import OCRResult, OCRBox

class PaddleOCRWrapper:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self.engine = None
        if not self.mock_mode:
            try:
                from paddleocr import PaddleOCR
                self.engine = PaddleOCR(use_angle_cls=True, lang='en')
            except ImportError:
                print("PaddleOCR not installed. Falling back to mock mode.")
                self.mock_mode = True
                
    def extract(self, image: np.ndarray) -> OCRResult:
        if self.mock_mode:
            return OCRResult(
                boxes=[OCRBox(text="MOCK_TEXT", confidence=0.95, bbox=(0,0,100,20))],
                mean_confidence=0.95,
                engine="paddleocr",
                raw_text="MOCK_TEXT"
            )
        
        result = self.engine.ocr(image, cls=True)
        if not result or not result[0]:
            return OCRResult(boxes=[], mean_confidence=0.0, engine="paddleocr", raw_text="")
            
        boxes = []
        conf_sum = 0.0
        texts = []
        for line in result[0]:
            bbox, (text, conf) = line
            x0 = int(min(pt[0] for pt in bbox))
            y0 = int(min(pt[1] for pt in bbox))
            x1 = int(max(pt[0] for pt in bbox))
            y1 = int(max(pt[1] for pt in bbox))
            
            boxes.append(OCRBox(text=text, confidence=conf, bbox=(x0, y0, x1, y1)))
            conf_sum += conf
            texts.append(text)
            
        return OCRResult(
            boxes=boxes,
            mean_confidence=conf_sum / len(boxes) if boxes else 0.0,
            engine="paddleocr",
            raw_text="\n".join(texts)
        )
