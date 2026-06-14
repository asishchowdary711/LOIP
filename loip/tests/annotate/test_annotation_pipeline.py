"""Phase 0 annotation-pipeline DoD gates (§10) — require the generated dataset corpus
and fine-tuned models, neither of which exist in this environment yet
(see project memory: data/ is empty, 10,500-sample corpus never generated)."""

import pytest


@pytest.mark.skip(
    reason="Requires the generated annotation corpus (scripts/annotate/generate_annotations.py "
    "output over the 10,500-sample document set), which has not been generated in this "
    "environment (data/ is empty)."
)
def test_annotation_bboxes_cover_all_gt_fields():
    pass


@pytest.mark.skip(
    reason="scripts/training/finetune_layoutlmv3.py exists and is runnable in .venv-ml, but "
    "the F1 >= 0.90 gate assumed the cancelled 10,500-doc corpus; on the 25-doc sample "
    "this is a calibration/smoke-test run only (see docs/DATA_GUIDANCE_NOTES.md) and has "
    "not been executed in this environment (no transformers/torch in .venv-ml)."
)
def test_layoutlmv3_finetune_f1_gte_0_90():
    pass


@pytest.mark.skip(
    reason="scripts/evaluate_qwen_docvqa.py exists (ANLS math unit-tested in "
    "tests/models/test_evaluate_qwen_docvqa.py), but requires a held-out DocVQA QA set "
    "(not downloaded, see docs/DATA_GUIDANCE_NOTES.md) and Qwen2.5-VL weights in "
    ".venv-ml; not executed in this environment."
)
def test_qwen_anls_gte_0_75():
    pass
