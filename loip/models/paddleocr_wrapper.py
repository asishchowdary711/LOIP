import logging
import numpy as np
from loip.domains.document_intel.schemas import OCRResult, OCRBox

logger = logging.getLogger(__name__)


class PaddleOCRWrapper:
    """Thin adapter for PaddleOCR. Compatible with PaddleOCR 3.x — the v2 API
    (`engine.ocr(img, cls=True)`) was replaced by `engine.predict(img)` and the
    `use_angle_cls=True` constructor arg became `use_textline_orientation=True`.
    """

    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self.engine = None
        if not self.mock_mode:
            try:
                from paddleocr import PaddleOCR

                self.engine = PaddleOCR(use_textline_orientation=True, lang='en')
            except ImportError:
                logger.warning("PaddleOCR not installed. Falling back to mock mode.")
                self.mock_mode = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("PaddleOCR init failed (%s). Falling back to mock mode.", exc)
                self.mock_mode = True

    def extract(self, image: np.ndarray) -> OCRResult:
        if self.mock_mode:
            return OCRResult(
                boxes=[OCRBox(text="MOCK_TEXT", confidence=0.95, bbox=(0, 0, 100, 20))],
                mean_confidence=0.95,
                engine="paddleocr",
                raw_text="MOCK_TEXT",
            )

        try:
            result = self.engine.predict(image)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PaddleOCR predict failed: %s", exc)
            return OCRResult(boxes=[], mean_confidence=0.0, engine="paddleocr", raw_text="")

        if not result:
            return OCRResult(boxes=[], mean_confidence=0.0, engine="paddleocr", raw_text="")

        page = result[0]
        rec_texts = page.get("rec_texts") or []
        rec_scores = page.get("rec_scores") or []
        rec_polys = page.get("rec_polys") or page.get("rec_boxes") or []

        boxes: list[OCRBox] = []
        for i, text in enumerate(rec_texts):
            conf = float(rec_scores[i]) if i < len(rec_scores) else 0.0
            bbox = (0, 0, 0, 0)
            if i < len(rec_polys):
                poly = rec_polys[i]
                try:
                    pts = np.asarray(poly).reshape(-1, 2)
                    x0 = int(pts[:, 0].min())
                    y0 = int(pts[:, 1].min())
                    x1 = int(pts[:, 0].max())
                    y1 = int(pts[:, 1].max())
                    bbox = (x0, y0, x1, y1)
                except Exception:  # noqa: BLE001
                    pass
            boxes.append(OCRBox(text=text, confidence=conf, bbox=bbox))

        mean_conf = (sum(b.confidence for b in boxes) / len(boxes)) if boxes else 0.0
        return OCRResult(
            boxes=boxes,
            mean_confidence=mean_conf,
            engine="paddleocr",
            raw_text="\n".join(rec_texts),
        )
