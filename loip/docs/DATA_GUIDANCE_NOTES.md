# DATA GUIDANCE NOTES

Explicit notes on dataset sourcing decisions, domain mismatches, and the
annotation pipeline rationale — so future contributors don't re-attempt
downloads or runs that were deliberately deferred or cancelled.

## ✅ Scope decision — 25-doc annotation sample is sufficient (10,500 NOT required)

**Accepted by stakeholder:** the full 10,500-document annotation corpus from
build-plan §5.4 is **not required**. The **25-document mixed sample**
(`data/annotation_sample25/`, ~80.5% average field-match rate across all 6
document types) is the agreed annotation set for this project. Do not
re-attempt the full-corpus annotation run. Any future model fine-tuning should
use the 25-doc sample (or generate a small additional batch if needed), and the
§10 annotation gates are treated as calibration/smoke checks against this
sample, not production gates against the (not-required) full corpus. The
machine-readable record of this decision is in `data/manifest.json`.

## Download budget — keep external datasets under 500 MB to 1 GB total

For this workspace snapshot, external public dataset downloads should stay
well below the multi-gigabyte originals. The practical local budget is **no
more than 500 MB to 1 GB total**, so only lightweight datasets should be
fetched directly into `loip/data/`. At the moment that means:

- `FUNSD` can be downloaded locally.
- `MIDV-500`, `MIDV-2020`, `RVL-CDIP`, and `DocVQA` remain deferred because
  their official distributions are far beyond the local cap or require special
  access.

If a future run needs more coverage, prefer documenting the source and keeping
the raw download out of this repo snapshot unless the storage budget changes.

## Regenerating loip/data/ in a new environment (e.g. Codespaces)

`loip/data/` is mostly **not tracked in git** — the full annotation corpus
(222MB, 10,500 docs) and FUNSD download (29MB) could not be pushed from the
original development machine's connection (~30-60KB/s, hits GitHub's push
timeout above ~2MB). Only `data/manifest.json`, `data/training/`, and
`data/annotation_sample25/` (the 25-doc input set) are tracked.

To restore the rest in a fresh clone with normal bandwidth:

```bash
cd loip
# FUNSD + archives (~46MB)
.venv/bin/python scripts/download_datasets.py

# Full 10,500-doc synthetic annotation corpus (~222MB; takes a few minutes)
.venv/bin/python scripts/generate_corpus.py

# Re-annotate the 25-doc sample (requires .venv-ocr, see SETUP.md) -> data/annotation_sample25_out/
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True .venv-ocr/bin/python -m scripts.annotate.generate_annotations \
    -i data/annotation_sample25/<doc_type> -o data/annotation_sample25_out/<doc_type>
```

MIDV-500/2020, RVL-CDIP, and DocVQA remain out of scope as described below
regardless of bandwidth (404'd URLs, disk size, or auth requirements).

## MIDV-500 / MIDV-2020 — not downloaded

`scripts/download_datasets.py`'s URLs
(`https://ftp.smartengines.com/midv-500/dataset/midv-500.zip` and the
MIDV-2020 equivalent) return **404** — the real datasets are distributed as
50+ per-document-type zips (~650MB each, ~32GB total for MIDV-500 alone) via
FTP, not a single archive.

**Domain mismatch**: MIDV-500/2020 contain European/Russian ID documents.
Per the build plan, their role is **OCR-robustness testing only** — they are
explicitly **not** used for Indian-document training (PAN/Aadhaar/salary
slips/etc.). Given:

1. The 404'd download would require a script rewrite for per-file FTP
   downloads, and
2. ~32GB+ exceeds available disk on this development machine (~37GB free),
   and
3. They are lowest-priority per the build plan anyway,

**this download is deferred indefinitely, not attempted.**

## RVL-CDIP — partial subset downloaded (320 images), full 38.7GB archive deferred

The full archive (`aharley/rvl_cdip` on HuggingFace, `data/rvl-cdip.tar.gz`,
38,762,320,458 bytes) was re-checked: it is **not gated** (contrary to the
earlier assumption), but at 38.7GB it would consume most of the ~11GB free on
this machine. Additionally, `datasets>=5.0` can no longer load this repo via
`load_dataset(..., streaming=True)` — it errors with `RuntimeError: Dataset
scripts are no longer supported, but found rvl_cdip.py` (the repo uses a
legacy loading script unsupported by modern `datasets`).

**Decision**: rather than the full corpus, `scripts/download_rvlcdip_subset.py`
streams the tar.gz directly via `requests` + `tarfile.open(fileobj=..., mode="r|gz")`
— reading sequentially and extracting only matching files, without ever
writing the full archive to disk. Labels come from `data/train.txt`
(13.7MB, downloaded in full). The script stops once each of the 16 classes
has reached a target count (default 20/class = 320 images) or a safety
byte/time budget is hit.

The resulting subset (`data/rvl_cdip_subset/`, 320 images / 38.6MB,
class-balanced 20-per-category, manifest at
`data/rvl_cdip_subset/manifest.json`) is a **LayoutLMv3 backbone fine-tuning
smoke sample only** — same role/caveat as the 25-doc annotation sample above:
it validates the fine-tuning pipeline end-to-end across all 16 RVL-CDIP
categories, not a substitute for the full 400K-document corpus. Re-run the
script with a larger `--per-class`/`--max-mb` if a bigger sample is needed
later; the full 38.7GB archive remains out of scope.

## DocVQA — not downloaded

The source (`rrc.cvc.uab.es`) requires a registered account/login for direct
download — `download_datasets.py` would 401/403 without manual credential
setup. Not attempted.

## Annotation corpus — 25-doc sample, not the full 10,500

`scripts/generate_corpus.py` generated the full §5.4 10,500-document
synthetic corpus into `data/annotation_corpus/` (222MB: pan_card 1500,
aadhaar 1500, salary_slip 3000, bank_statement 3000, form16 750, itr 750,
clean/tampered split per the build plan table).

Running the full LayoutLMv3/Donut annotation pass
(`scripts/annotate/generate_annotations.py`) against all 10,500 documents
was **started, then cancelled** — per-document timing is highly variable
(PAN ~3s/doc, but bank_statement docs with thousands of OCR tokens take much
longer), making the full run **multi-day** single-process, not the
originally estimated 5-10hrs.

**Decision**: a 25-document mixed sample (5 pan_card, 5 aadhaar, 5
salary_slip, 5 bank_statement, 3 form16, 2 itr —
`data/annotation_sample25/` → `data/annotation_sample25_out/`) was annotated
instead, achieving an **80.5% average field-match rate**:

| Doc type | Match rate |
|---|---|
| pan_card | 100% (4/4 fields, all 5 docs) |
| form16 | 100% (6/6 fields, all 3 docs) |
| salary_slip | ~98% (11.4/12 avg) |
| aadhaar | ~74% (7-8/10) |
| itr | 1.5/2 avg |
| bank_statement | ~38-46% (weakest — transaction-table row matching gap) |

This 25-doc sample is considered **sufficient** for current purposes (e.g.
validating the annotation pipeline end-to-end across all 6 document types).
**The full 10,500-doc corpus annotation run is cancelled, not just
deferred** — any future ML training (LayoutLMv3 fine-tuning, etc.) should
use the 25-doc sample or generate a small additional batch if needed, rather
than re-attempting the full corpus.

### Known remaining annotation gaps (not blocking)

- **Aadhaar number fuzzy-match**: OCR reads the 12-digit Aadhaar number as 3
  space-separated 4-digit groups (`"5187 6834 4248"`) vs the ground truth's
  contiguous 12-digit string. `_is_exact_field` only strips commas/colons,
  not spaces, before comparing.
- **Bank statement transaction rows** (`txn_N_*` fields): poor match rate,
  likely needs row-grouping by y-coordinate before token matching, rather
  than flat line-by-line OCR order.
- **ITR fields**: 1/2 fields matched on the sample — not yet investigated.

## FUNSD — downloaded

`data/funsd/` (16.8MB) was downloaded successfully via
`scripts/download_datasets.py` and is available for use.

## LayoutLMv3 / Donut fine-tuning — 25-doc sample is calibration only, not the F1 >= 0.90 gate

`scripts/training/finetune_layoutlmv3.py` and
`scripts/training/finetune_donut.py` fine-tune on the same 25-document
annotation sample described above (`data/annotation_sample25_out/`), split
20 train / 5 val (`train_test_split(..., test_size=5, random_state=42)`,
**not stratified** — `itr` has only 2 total examples, which is below
sklearn's minimum for a stratified split across 6 classes).

The build plan's `F1 >= 0.90` gate
(`tests/annotate/test_annotation_pipeline.py::test_layoutlmv3_finetune_f1_gte_0_90`)
assumed the (cancelled) 10,500-doc corpus. On 25 docs — with a 5-doc
validation split spanning 6 classes — this fine-tune is a **smoke
test/calibration run only**: it confirms the training loop, label mapping,
and bbox-normalization code are correct end-to-end, not that the model meets
production accuracy. The script reports its actual val accuracy/F1 when run;
record that number, but don't treat it as a pass/fail gate until run against
a larger, properly-stratified corpus (the full 10,500-doc corpus, or a new
larger sample — see "Annotation corpus" above for why the full corpus run
was cancelled).

`scripts/training/finetune_donut.py` carries the same caveat and is lower
priority — `DonutWrapper` falls back to the zero-shot
`naver-clova-ix/donut-base` checkpoint if its fine-tune has not been run.
