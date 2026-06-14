import json
import re

import numpy as np

from loip.domains.document_intel.schemas import FIELD_SPECS, DocumentClass, ExtractionField, ExtractionResult

# Default model — configurable via constructor for smaller/larger variants
# (e.g. "Qwen/Qwen2.5-VL-7B-Instruct").
DEFAULT_MODEL = "Qwen/Qwen2.5-VL-3B-Instruct"

# Confidence when the model returns a complete, well-formed JSON object
# containing every expected field.
FULL_MATCH_CONFIDENCE = 0.90
# Confidence when JSON parses but is missing some expected fields.
PARTIAL_MATCH_CONFIDENCE = 0.70


class Qwen25VLWrapper:
    def __init__(self, mock_mode: bool = True, model_name: str = DEFAULT_MODEL):
        self.mock_mode = mock_mode
        self.model_name = model_name
        self.processor = None
        self.model = None

        if not self.mock_mode:
            try:
                from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

                self.processor = AutoProcessor.from_pretrained(self.model_name)
                self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                    self.model_name, torch_dtype="auto", device_map="auto",
                )
                self.model.eval()
            except ImportError:
                self.mock_mode = True

    @staticmethod
    def _parse_json(text: str) -> dict:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return {}

    def extract_fields(self, image: np.ndarray, doc_class: DocumentClass) -> ExtractionResult:
        if self.mock_mode:
            fields = []
            if doc_class == DocumentClass.SALARY_SLIP:
                fields = [
                    ExtractionField(name="employer_name", value="Acme Corp", confidence=0.95),
                    ExtractionField(name="net_pay", value="50000", confidence=0.98),
                ]
            elif doc_class == DocumentClass.PAN:
                fields = [
                    ExtractionField(name="pan_number", value="ABCDE1234F", confidence=0.99),
                    ExtractionField(name="full_name", value="Mock User", confidence=0.99),
                    ExtractionField(name="date_of_birth", value="01/01/1990", confidence=0.99),
                ]
            elif doc_class == DocumentClass.AADHAAR:
                fields = [
                    # Verhoeff-valid 12-digit Aadhaar (passes loip.validation.is_valid_aadhaar)
                    ExtractionField(name="aadhaar_number", value="234123412346", confidence=0.99),
                ]
            elif doc_class == DocumentClass.ITR:
                fields = [
                    ExtractionField(name="total_income", value="800000", confidence=0.95),
                ]
            elif doc_class == DocumentClass.GST_RETURN:
                fields = [
                    ExtractionField(name="turnover_b2b", value="5000000", confidence=0.90),
                    ExtractionField(name="turnover_b2c", value="1000000", confidence=0.90),
                ]
            return ExtractionResult(
                document_class=doc_class,
                fields=fields,
                model="qwen2.5-vl",
                overall_confidence=0.96
            )

        import torch
        from PIL import Image as PILImage

        field_names = FIELD_SPECS.get(doc_class, [])
        pil_image = PILImage.fromarray(image).convert("RGB")

        prompt = (
            "Extract the following fields from this document image and return "
            "ONLY a JSON object with these exact keys: "
            f"{', '.join(field_names)}. "
            "If a field is not visible or not present, use an empty string as its value."
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": pil_image},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.processor(text=[text], images=[pil_image], return_tensors="pt").to(self.model.device)

        with torch.no_grad():
            output_ids = self.model.generate(**inputs, max_new_tokens=512)

        generated_ids = output_ids[:, inputs["input_ids"].shape[1]:]
        response = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0]

        parsed = self._parse_json(response)
        if not parsed:
            return ExtractionResult(document_class=doc_class, fields=[], model="qwen2.5-vl", overall_confidence=0.0)

        found_all = all(name in parsed for name in field_names)
        confidence = FULL_MATCH_CONFIDENCE if found_all else PARTIAL_MATCH_CONFIDENCE

        fields = [
            ExtractionField(name=name, value=str(parsed[name]), confidence=confidence)
            for name in field_names
            if parsed.get(name)
        ]
        overall_confidence = confidence if fields else 0.0
        return ExtractionResult(document_class=doc_class, fields=fields, model="qwen2.5-vl", overall_confidence=overall_confidence)
