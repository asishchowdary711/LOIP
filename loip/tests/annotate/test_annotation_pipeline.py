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
    reason="Requires a fine-tuned LayoutLMv3 model evaluated on a held-out Indian document "
    "set; no fine-tuning has occurred (models are mock_mode stubs)."
)
def test_layoutlmv3_finetune_f1_gte_0_90():
    pass


@pytest.mark.skip(
    reason="Requires scripts/evaluate_qwen_docvqa.py and a held-out DocVQA set to compute "
    "ANLS; the evaluation script does not exist yet and Qwen2.5-VL is a mock_mode stub."
)
def test_qwen_anls_gte_0_75():
    pass
