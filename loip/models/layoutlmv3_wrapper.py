from pathlib import Path

import numpy as np

from loip.domains.document_intel.schemas import ClassificationResult, DocumentClass

CHECKPOINT_DIR = Path(__file__).resolve().parent / "checkpoints" / "layoutlmv3-finetuned"
BASE_MODEL = "microsoft/layoutlmv3-base"

# Classification head label order — must match
# scripts/training/finetune_layoutlmv3.py and the document types present in
# data/annotation_sample25_out/ (the only types with annotated training data
# so far).
DOC_CLASS_LABELS = [
    DocumentClass.AADHAAR,
    DocumentClass.BANK_STATEMENT,
    DocumentClass.FORM16,
    DocumentClass.ITR,
    DocumentClass.PAN,
    DocumentClass.SALARY_SLIP,
]


class LayoutLMv3Wrapper:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self.processor = None
        self.model = None
        self._ocr = None

        if not self.mock_mode:
            try:
                from transformers import LayoutLMv3ForSequenceClassification, LayoutLMv3Processor

                if CHECKPOINT_DIR.exists():
                    checkpoint = str(CHECKPOINT_DIR)
                    self.model = LayoutLMv3ForSequenceClassification.from_pretrained(checkpoint)
                else:
                    checkpoint = BASE_MODEL
                    self.model = LayoutLMv3ForSequenceClassification.from_pretrained(
                        checkpoint, num_labels=len(DOC_CLASS_LABELS)
                    )
                self.processor = LayoutLMv3Processor.from_pretrained(checkpoint, apply_ocr=False)
                self.model.eval()
            except ImportError:
                self.mock_mode = True

    def _get_ocr(self):
        if self._ocr is None:
            from loip.models.paddleocr_wrapper import PaddleOCRWrapper
            self._ocr = PaddleOCRWrapper(mock_mode=False)
        return self._ocr

    @staticmethod
    def _normalize_bbox(bbox: tuple[int, int, int, int], height: int, width: int) -> list[int]:
        x0, y0, x1, y1 = bbox
        return [
            int(1000 * x0 / width), int(1000 * y0 / height),
            int(1000 * x1 / width), int(1000 * y1 / height),
        ]

    def classify(self, image: np.ndarray) -> ClassificationResult:
        if self.mock_mode:
            h = image.shape[0]
            if h == 100:
                doc_class = DocumentClass.PAN
            elif h == 101:
                doc_class = DocumentClass.AADHAAR
            elif h == 102:
                doc_class = DocumentClass.SALARY_SLIP
            else:
                doc_class = DocumentClass.SALARY_SLIP

            return ClassificationResult(
                document_class=doc_class,
                confidence=0.98,
                needs_review=False,
                logits={doc_class.value: 0.98, "other": 0.01},
            )

        import torch
        from PIL import Image

        ocr_result = self._get_ocr().extract(image)
        height, width = image.shape[0], image.shape[1]
        if ocr_result.boxes:
            words = [box.text for box in ocr_result.boxes]
            boxes = [self._normalize_bbox(box.bbox, height, width) for box in ocr_result.boxes]
        else:
            words = [""]
            boxes = [[0, 0, 0, 0]]

        pil_image = Image.fromarray(image).convert("RGB")
        encoding = self.processor(pil_image, words, boxes=boxes, return_tensors="pt", truncation=True)

        with torch.no_grad():
            outputs = self.model(**encoding)
            probs = torch.nn.functional.softmax(outputs.logits, dim=-1)[0]

        pred_idx = int(torch.argmax(probs).item())
        doc_class = DOC_CLASS_LABELS[pred_idx]
        confidence = float(probs[pred_idx].item())
        logits = {label.value: float(probs[i].item()) for i, label in enumerate(DOC_CLASS_LABELS)}

        return ClassificationResult(
            document_class=doc_class,
            confidence=confidence,
            needs_review=False,
            logits=logits,
        )
