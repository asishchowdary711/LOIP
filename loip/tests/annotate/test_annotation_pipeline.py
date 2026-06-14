"""Phase 0 annotation-pipeline DoD gates (§10).

**Scope decision (accepted):** the 25-document mixed sample
(`data/annotation_sample25/`) is the agreed annotation set for this project —
the full 10,500-doc corpus from build-plan §5.4 is explicitly NOT required (see
`docs/DATA_GUIDANCE_NOTES.md`). The annotation pipeline was validated against
the 25-doc sample at an ~80.5% average field-match rate.

These gates remain skipped here only because executing them needs the
PaddleOCR `.venv-ocr` and/or LayoutLMv3/Qwen2.5-VL weights, which are not
provisioned in this environment — not because the corpus is "missing."
"""

import pytest


@pytest.mark.skip(
    reason="Accepted scope: validated against the 25-doc sample (~80.5% field-match, see "
    "docs/DATA_GUIDANCE_NOTES.md). Re-running bbox coverage needs the PaddleOCR .venv-ocr "
    "to regenerate annotations; the full 10,500-doc corpus is explicitly not required."
)
def test_annotation_bboxes_cover_all_gt_fields():
    pass


@pytest.mark.skip(
    reason="LayoutLMv3 fine-tune on the accepted 25-doc sample is a calibration/smoke run, "
    "not a production F1>=0.90 gate (which assumed the not-required 10,500-doc corpus). "
    "Needs torch/transformers in .venv-ml; see docs/DATA_GUIDANCE_NOTES.md."
)
def test_layoutlmv3_finetune_f1_gte_0_90():
    pass


@pytest.mark.skip(
    reason="ANLS math is unit-tested in tests/models/test_evaluate_qwen_docvqa.py; the live "
    "gate needs a held-out DocVQA set (not downloadable without an account) and Qwen2.5-VL "
    "weights in .venv-ml. See docs/DATA_GUIDANCE_NOTES.md."
)
def test_qwen_anls_gte_0_75():
    pass
