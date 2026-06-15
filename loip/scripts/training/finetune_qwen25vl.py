"""LoRA fine-tune Qwen2.5-VL-3B-Instruct for field extraction on PAN + Aadhaar
from the 25-doc annotation sample.

This is a CALIBRATION / SMOKE-TEST fine-tune, not a production model — only
10 documents (5 PAN + 5 Aadhaar) are available (see docs/DATA_GUIDANCE_NOTES.md).
A LoRA adapter is trained on top of the frozen base model so the resulting
checkpoint is small; Qwen25VLWrapper falls back to the zero-shot
`Qwen/Qwen2.5-VL-3B-Instruct` checkpoint if this adapter is absent.

Requires `transformers`, `torch`, `peft`, `accelerate`, and `Pillow` in
.venv-ml (see docs/RUNBOOK.md "Phase B activation").

Run with: .venv-ml/bin/python -m scripts.training.finetune_qwen25vl
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import torch
from PIL import Image
from peft import LoraConfig, get_peft_model
from sklearn.model_selection import train_test_split
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

from loip.models.qwen2_5_vl_wrapper import DEFAULT_MODEL

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "annotation_sample25_out"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKPOINT_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "checkpoints" / "qwen25vl-finetuned"

DOC_TYPES = {"pan", "aadhaar"}
EPOCHS = 3
LEARNING_RATE = 1e-4
VAL_SIZE = 2

PROMPT_TEMPLATE = (
    "Extract the following fields from this document image and return "
    "ONLY a JSON object with these exact keys: {fields}. "
    "If a field is not visible or not present, use an empty string as its value."
)


def _load_examples() -> list[dict]:
    examples = []
    for path in sorted(glob.glob(str(DATA_DIR / "*_donut.json"))):
        with open(path) as f:
            doc = json.load(f)

        if doc["document_type"] not in DOC_TYPES:
            continue

        gt_parse = doc["gt_parse"]
        prompt = PROMPT_TEMPLATE.format(fields=", ".join(gt_parse.keys()))
        target = json.dumps(gt_parse, ensure_ascii=False)
        image_path = REPO_ROOT / doc["image_path"]
        examples.append({
            "document_id": doc["document_id"],
            "document_type": doc["document_type"],
            "image_path": str(image_path),
            "prompt": prompt,
            "target": target,
            "gt_parse": gt_parse,
        })

    return examples


def _prepare_inputs(example: dict, processor: AutoProcessor) -> tuple[dict, int]:
    """Build model inputs and labels (prompt tokens masked with -100)."""
    image = Image.open(example["image_path"]).convert("RGB")

    user_message = [{"role": "user", "content": [
        {"type": "image", "image": image}, {"type": "text", "text": example["prompt"]},
    ]}]
    full_messages = user_message + [{"role": "assistant", "content": [{"type": "text", "text": example["target"]}]}]

    prompt_text = processor.apply_chat_template(user_message, tokenize=False, add_generation_prompt=True)
    full_text = processor.apply_chat_template(full_messages, tokenize=False, add_generation_prompt=False)

    prompt_inputs = processor(text=[prompt_text], images=[image], return_tensors="pt")
    full_inputs = processor(text=[full_text], images=[image], return_tensors="pt")

    prompt_len = prompt_inputs["input_ids"].shape[1]
    labels = full_inputs["input_ids"].clone()
    labels[:, :prompt_len] = -100

    full_inputs["labels"] = labels
    return full_inputs, prompt_len


def _device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def main() -> None:
    examples = _load_examples()
    train_examples, val_examples = train_test_split(examples, test_size=VAL_SIZE, random_state=42, shuffle=True)
    print(f"train={len(train_examples)} val={len(val_examples)}")

    processor = AutoProcessor.from_pretrained(DEFAULT_MODEL)
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(DEFAULT_MODEL, torch_dtype=torch.bfloat16)

    lora_config = LoraConfig(
        r=8, lora_alpha=16, lora_dropout=0.05, bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    device = _device()
    model.to(device)

    optimizer = torch.optim.AdamW(
        (p for p in model.parameters() if p.requires_grad), lr=LEARNING_RATE,
    )

    model.train()
    for epoch in range(EPOCHS):
        total_loss = 0.0
        for example in train_examples:
            inputs, _ = _prepare_inputs(example, processor)
            inputs = {k: v.to(device) for k, v in inputs.items()}
            outputs = model(**inputs)
            outputs.loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            total_loss += outputs.loss.item()
        print(f"epoch {epoch + 1}/{EPOCHS}: train_loss={total_loss / len(train_examples):.4f}")

    model.eval()
    val_loss = 0.0
    with torch.no_grad():
        for example in val_examples:
            inputs, _ = _prepare_inputs(example, processor)
            inputs = {k: v.to(device) for k, v in inputs.items()}
            val_loss += model(**inputs).loss.item()
    print(f"[qwen25vl] val_loss: {val_loss / len(val_examples):.4f} (n_val={len(val_examples)})")

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(CHECKPOINT_DIR))
    processor.save_pretrained(str(CHECKPOINT_DIR))
    print(f"Saved LoRA adapter to {CHECKPOINT_DIR}")


if __name__ == "__main__":
    main()
