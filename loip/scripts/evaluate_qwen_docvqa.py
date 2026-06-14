"""Evaluate Qwen2.5-VL field extraction against a DocVQA-style QA set using ANLS.

Computes the Average Normalized Levenshtein Similarity (ANLS) metric used by
the DocVQA benchmark. The build plan's gate is
ANLS >= ANLS_GATE_THRESHOLD (0.75, see domains/document_intel/schemas.py).

The ANLS math (`evaluate`, `question_score`, `normalized_similarity`) is
pure Python and runnable/unit-testable now with synthetic QA pairs — see
tests/models/test_evaluate_qwen_docvqa.py. Running `main()` against a real
DocVQA holdout set requires Qwen2.5-VL weights in .venv-ml — deferred to the
production phase (see docs/RUNBOOK.md "Phase B activation").

Run with: .venv-ml/bin/python -m scripts.evaluate_qwen_docvqa --qa-file <path/to/qa.json>
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import click

from loip.domains.document_intel.schemas import ANLS_GATE_THRESHOLD, DocumentClass

# Per DocVQA convention, an NLS below this is clamped to 0.
ANLS_CLAMP_THRESHOLD = 0.5


@dataclass
class QAPair:
    image_path: str
    document_class: DocumentClass
    question: str
    answers: list[str]  # one or more acceptable ground-truth answers


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    previous_row = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current_row = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            current_row.append(min(
                previous_row[j] + 1,       # deletion
                current_row[j - 1] + 1,    # insertion
                previous_row[j - 1] + cost,  # substitution
            ))
        previous_row = current_row
    return previous_row[-1]


def normalized_similarity(prediction: str, ground_truth: str) -> float:
    prediction = prediction.strip().lower()
    ground_truth = ground_truth.strip().lower()
    max_len = max(len(prediction), len(ground_truth))
    if max_len == 0:
        return 1.0
    nls = 1.0 - _levenshtein(prediction, ground_truth) / max_len
    return nls if nls >= ANLS_CLAMP_THRESHOLD else 0.0


def question_score(prediction: str, ground_truths: list[str]) -> float:
    return max(normalized_similarity(prediction, gt) for gt in ground_truths)


def evaluate(qa_pairs: list[QAPair], predictions: list[str]) -> float:
    if len(qa_pairs) != len(predictions):
        raise ValueError("qa_pairs and predictions must be the same length")
    if not qa_pairs:
        return 0.0
    scores = [question_score(pred, qa.answers) for qa, pred in zip(qa_pairs, predictions, strict=True)]
    return sum(scores) / len(scores)


def _run_qwen(qa_pairs: list[QAPair], model_name: str) -> list[str]:
    """Run Qwen2.5-VL over each QA pair's image+question, returning raw text answers.

    Requires transformers/torch/Pillow in .venv-ml — deferred to the
    production phase (see docs/RUNBOOK.md "Phase B activation").
    """
    import torch
    from PIL import Image
    from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

    processor = AutoProcessor.from_pretrained(model_name)
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        model_name, torch_dtype="auto", device_map="auto",
    )
    model.eval()

    predictions = []
    for qa in qa_pairs:
        image = Image.open(qa.image_path).convert("RGB")
        messages = [{
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": qa.question},
            ],
        }]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[text], images=[image], return_tensors="pt").to(model.device)

        with torch.no_grad():
            output_ids = model.generate(**inputs, max_new_tokens=64)

        generated_ids = output_ids[:, inputs["input_ids"].shape[1]:]
        response = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        predictions.append(response.strip())

    return predictions


@click.command()
@click.option("--qa-file", required=True, type=click.Path(exists=True),
              help="JSON file containing a list of QA pair objects "
                   "(image_path, document_class, question, answers).")
@click.option("--model-name", default="Qwen/Qwen2.5-VL-3B-Instruct", show_default=True)
def main(qa_file: str, model_name: str) -> None:
    with open(qa_file) as f:
        raw = json.load(f)

    qa_pairs = [
        QAPair(
            image_path=r["image_path"],
            document_class=DocumentClass(r["document_class"]),
            question=r["question"],
            answers=r["answers"],
        )
        for r in raw
    ]

    predictions = _run_qwen(qa_pairs, model_name)
    anls = evaluate(qa_pairs, predictions)

    status = "PASS" if anls >= ANLS_GATE_THRESHOLD else "FAIL"
    click.echo(f"ANLS: {anls:.4f} (gate >= {ANLS_GATE_THRESHOLD}) -> {status}")


if __name__ == "__main__":
    main()
