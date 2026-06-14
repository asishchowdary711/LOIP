import re
from pathlib import Path

import numpy as np

from loip.domains.document_intel.schemas import FIELD_SPECS, DocumentClass, ExtractionField, ExtractionResult

CHECKPOINT_DIR = Path(__file__).resolve().parent / "checkpoints" / "donut-finetuned"
BASE_MODEL = "naver-clova-ix/donut-base"

# Custom task token marking the start of a LOIP document-parsing sequence —
# must match scripts/training/finetune_donut.py.
TASK_PROMPT = "<s_loip>"

# Field-name special tokens registered during fine-tuning, derived from every
# field across FIELD_SPECS (so <s_FIELD>/</s_FIELD> tokens exist for any
# document type the model might see).
ALL_FIELD_NAMES = sorted({name for names in FIELD_SPECS.values() for name in names})

MOCK_CONFIDENCE = 0.85
REAL_FIELD_CONFIDENCE = 0.75


class DonutWrapper:
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self.processor = None
        self.model = None

        if not self.mock_mode:
            try:
                from transformers import DonutProcessor, VisionEncoderDecoderModel

                checkpoint = str(CHECKPOINT_DIR) if CHECKPOINT_DIR.exists() else BASE_MODEL
                self.processor = DonutProcessor.from_pretrained(checkpoint)
                self.model = VisionEncoderDecoderModel.from_pretrained(checkpoint)
                self.model.eval()
            except ImportError:
                self.mock_mode = True

    def extract_structured(self, image: np.ndarray, doc_class: DocumentClass) -> ExtractionResult:
        if self.mock_mode:
            return ExtractionResult(
                document_class=doc_class,
                fields=[ExtractionField(name="fallback_field", value="mock_value", confidence=MOCK_CONFIDENCE)],
                model="donut",
                overall_confidence=MOCK_CONFIDENCE,
            )

        import torch
        from PIL import Image

        pil_image = Image.fromarray(image).convert("RGB")
        pixel_values = self.processor(pil_image, return_tensors="pt").pixel_values

        decoder_input_ids = self.processor.tokenizer(
            TASK_PROMPT, add_special_tokens=False, return_tensors="pt",
        ).input_ids

        with torch.no_grad():
            outputs = self.model.generate(
                pixel_values,
                decoder_input_ids=decoder_input_ids,
                max_length=self.model.decoder.config.max_position_embeddings,
                pad_token_id=self.processor.tokenizer.pad_token_id,
                eos_token_id=self.processor.tokenizer.eos_token_id,
                return_dict_in_generate=True,
            )

        sequence = self.processor.batch_decode(outputs.sequences)[0]
        sequence = sequence.replace(self.processor.tokenizer.eos_token, "")
        sequence = sequence.replace(self.processor.tokenizer.pad_token, "")
        sequence = re.sub(r"^<s_loip>", "", sequence).strip()

        parsed = self.processor.token2json(sequence)

        expected_fields = FIELD_SPECS.get(doc_class, [])
        fields = [
            ExtractionField(name=name, value=str(parsed[name]), confidence=REAL_FIELD_CONFIDENCE)
            for name in expected_fields
            if name in parsed and parsed[name]
        ]

        overall_confidence = (len(fields) / len(expected_fields)) * REAL_FIELD_CONFIDENCE if expected_fields else 0.0
        return ExtractionResult(document_class=doc_class, fields=fields, model="donut", overall_confidence=overall_confidence)
