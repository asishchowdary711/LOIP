"""Fine-tune Donut for structured field extraction on the 25-doc annotation sample.

CALIBRATION / SMOKE-TEST only — see scripts/training/finetune_layoutlmv3.py
and docs/DATA_GUIDANCE_NOTES.md for the same caveat (25 docs vs. the
cancelled 10,500-doc corpus). Lower priority than the LayoutLMv3 fine-tune;
DonutWrapper falls back to the zero-shot `naver-clova-ix/donut-base`
checkpoint if this has not been run.

Requires `transformers`, `torch`, and `Pillow` in .venv-ml — not installed by
default (see docs/RUNBOOK.md "Phase B activation"). Execution is deferred
until the production phase; this script is written and ready to run.

Run with: .venv-ml/bin/python -m scripts.training.finetune_donut
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import torch
from PIL import Image
from sklearn.model_selection import train_test_split
from transformers import DonutProcessor, VisionEncoderDecoderModel

from loip.models.donut_wrapper import ALL_FIELD_NAMES, BASE_MODEL, CHECKPOINT_DIR, TASK_PROMPT

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "annotation_sample25_out"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

EPOCHS = 10
BATCH_SIZE = 1
LEARNING_RATE = 3e-5
VAL_SIZE = 5
MAX_LENGTH = 512


def _json2token(obj, sort_keys: bool = True) -> str:
    if isinstance(obj, dict):
        keys = sorted(obj.keys()) if sort_keys else obj.keys()
        return "".join(f"<s_{k}>{_json2token(obj[k], sort_keys)}</s_{k}>" for k in keys)
    if isinstance(obj, list):
        return "<sep/>".join(_json2token(item, sort_keys) for item in obj)
    return str(obj)


def _load_examples() -> list[dict]:
    examples = []
    for path in sorted(glob.glob(str(DATA_DIR / "*_donut.json"))):
        with open(path) as f:
            doc = json.load(f)

        target_sequence = TASK_PROMPT + _json2token(doc["gt_parse"]) + "</s>"
        image_path = REPO_ROOT / doc["image_path"]
        examples.append({"image_path": str(image_path), "target_sequence": target_sequence})

    return examples


class DonutDataset(torch.utils.data.Dataset):
    def __init__(self, examples: list[dict], processor: DonutProcessor):
        self.examples = examples
        self.processor = processor

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict:
        example = self.examples[idx]
        image = Image.open(example["image_path"]).convert("RGB")
        pixel_values = self.processor(image, return_tensors="pt").pixel_values.squeeze(0)

        labels = self.processor.tokenizer(
            example["target_sequence"], add_special_tokens=False,
            max_length=MAX_LENGTH, padding="max_length", truncation=True,
            return_tensors="pt",
        ).input_ids.squeeze(0)
        labels[labels == self.processor.tokenizer.pad_token_id] = -100

        return {"pixel_values": pixel_values, "labels": labels}


def _device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def main() -> None:
    examples = _load_examples()
    train_examples, val_examples = train_test_split(examples, test_size=VAL_SIZE, random_state=42, shuffle=True)

    processor = DonutProcessor.from_pretrained(BASE_MODEL)
    model = VisionEncoderDecoderModel.from_pretrained(BASE_MODEL)

    # Register the task prompt and every FIELD_SPECS field name as special
    # tokens so json2token sequences round-trip through token2json.
    field_tokens = [f"<s_{name}>" for name in ALL_FIELD_NAMES] + [f"</s_{name}>" for name in ALL_FIELD_NAMES]
    new_tokens = [TASK_PROMPT, "<sep/>", *field_tokens]
    processor.tokenizer.add_special_tokens({"additional_special_tokens": new_tokens})
    model.decoder.resize_token_embeddings(len(processor.tokenizer))

    model.config.pad_token_id = processor.tokenizer.pad_token_id
    model.config.decoder_start_token_id = processor.tokenizer.convert_tokens_to_ids(TASK_PROMPT)

    device = _device()
    model.to(device)

    train_loader = torch.utils.data.DataLoader(
        DonutDataset(train_examples, processor), batch_size=BATCH_SIZE, shuffle=True,
    )
    val_loader = torch.utils.data.DataLoader(
        DonutDataset(val_examples, processor), batch_size=BATCH_SIZE,
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)

    model.train()
    for epoch in range(EPOCHS):
        total_loss = 0.0
        for batch in train_loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            outputs = model(**batch)
            outputs.loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            total_loss += outputs.loss.item()
        print(f"epoch {epoch + 1}/{EPOCHS}: train_loss={total_loss / len(train_loader):.4f}")

    model.eval()
    val_loss = 0.0
    with torch.no_grad():
        for batch in val_loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            val_loss += model(**batch).loss.item()
    print(f"[donut] val_loss: {val_loss / len(val_loader):.4f} (n_val={len(val_examples)})")

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(CHECKPOINT_DIR))
    processor.save_pretrained(str(CHECKPOINT_DIR))
    print(f"Saved checkpoint to {CHECKPOINT_DIR}")


if __name__ == "__main__":
    main()
