"""Fine-tune LayoutLMv3 for document classification on the 25-doc annotation sample.

This is a CALIBRATION / SMOKE-TEST fine-tune, not a production model. The
build plan's F1 >= 0.90 classification gate assumed a 10,500-doc corpus that
was cancelled; on 25 docs (across 6 document types, one with only 2 samples)
the resulting metric is reported but not hard-gated. See
docs/DATA_GUIDANCE_NOTES.md for details.

Requires `transformers`, `torch`, and `Pillow` in .venv-ml — not installed by
default (see docs/RUNBOOK.md "Phase B activation"). Execution is deferred
until the production phase; this script is written and ready to run.

Run with: .venv-ml/bin/python -m scripts.training.finetune_layoutlmv3
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import torch
from PIL import Image
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from transformers import LayoutLMv3ForSequenceClassification, LayoutLMv3Processor

from loip.domains.document_intel.schemas import DocumentClass
from loip.models.layoutlmv3_wrapper import BASE_MODEL, CHECKPOINT_DIR, DOC_CLASS_LABELS

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "annotation_sample25_out"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

EPOCHS = 10
BATCH_SIZE = 2
LEARNING_RATE = 5e-5
VAL_SIZE = 5


class DocClassificationDataset(torch.utils.data.Dataset):
    def __init__(self, examples: list[dict], processor: LayoutLMv3Processor):
        self.examples = examples
        self.processor = processor

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict:
        example = self.examples[idx]
        image = Image.open(example["image_path"]).convert("RGB")
        encoding = self.processor(
            image, example["words"], boxes=example["boxes"],
            truncation=True, padding="max_length", max_length=512,
            return_tensors="pt",
        )
        item = {k: v.squeeze(0) for k, v in encoding.items()}
        item["labels"] = torch.tensor(example["label"], dtype=torch.long)
        return item


def _load_examples() -> list[dict]:
    examples = []
    for path in sorted(glob.glob(str(DATA_DIR / "*_layoutlmv3.json"))):
        with open(path) as f:
            doc = json.load(f)

        doc_class = DocumentClass(doc["document_type"])
        label = DOC_CLASS_LABELS.index(doc_class)

        width = doc["image_size"]["width"]
        height = doc["image_size"]["height"]
        words = [tok["text"] for tok in doc["tokens"]]
        boxes = [
            [
                int(1000 * tok["bbox"][0] / width), int(1000 * tok["bbox"][1] / height),
                int(1000 * tok["bbox"][2] / width), int(1000 * tok["bbox"][3] / height),
            ]
            for tok in doc["tokens"]
        ]
        if not words:
            words, boxes = [""], [[0, 0, 0, 0]]

        image_path = REPO_ROOT / doc["image_path"]
        examples.append({"image_path": str(image_path), "words": words, "boxes": boxes, "label": label})

    return examples


def _device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def main() -> None:
    examples = _load_examples()
    train_examples, val_examples = train_test_split(examples, test_size=VAL_SIZE, random_state=42, shuffle=True)

    processor = LayoutLMv3Processor.from_pretrained(BASE_MODEL, apply_ocr=False)
    model = LayoutLMv3ForSequenceClassification.from_pretrained(BASE_MODEL, num_labels=len(DOC_CLASS_LABELS))

    device = _device()
    model.to(device)

    train_loader = torch.utils.data.DataLoader(
        DocClassificationDataset(train_examples, processor), batch_size=BATCH_SIZE, shuffle=True,
    )
    val_loader = torch.utils.data.DataLoader(
        DocClassificationDataset(val_examples, processor), batch_size=BATCH_SIZE,
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
    all_preds: list[int] = []
    all_labels: list[int] = []
    with torch.no_grad():
        for batch in val_loader:
            labels = batch.pop("labels")
            batch = {k: v.to(device) for k, v in batch.items()}
            preds = model(**batch).logits.argmax(dim=-1).cpu()
            all_preds.extend(preds.tolist())
            all_labels.extend(labels.tolist())

    acc = accuracy_score(all_labels, all_preds)
    f1 = f1_score(all_labels, all_preds, average="macro")
    print(f"[layoutlmv3] val accuracy: {acc:.4f}, f1_macro: {f1:.4f} (n_val={len(val_examples)})")

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(CHECKPOINT_DIR))
    processor.save_pretrained(str(CHECKPOINT_DIR))
    print(f"Saved checkpoint to {CHECKPOINT_DIR}")


if __name__ == "__main__":
    main()
