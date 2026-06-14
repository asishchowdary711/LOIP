# RUNBOOK

Operational notes for running and troubleshooting LOIP locally.

## Starting the API

Launch from the **repo root** (`/workspaces/LOIP`), not from `loip/`, and
load the app as `loip.web.api:app`:

```bash
cd /workspaces/LOIP
PYTHONPATH=/workspaces/LOIP loip/.venv/bin/uvicorn loip.web.api:app --host 0.0.0.0 --port 8000
```

> **Why the full module path matters:** `loip/web/api.py` uses relative
> imports (`from .routes import ...`) while the pipeline imports
> `loip.web.routes.audit` absolutely. If the app is loaded as `web.api`
> instead of `loip.web.api`, those resolve to two *different* module objects
> with separate `review_processor` / explainability singletons, so the
> review queue shows up empty. Always load `loip.web.api`.

On startup the app seeds 7 demo review cases (`loip/web/startup.py`,
mock-mode) so the review console has data immediately. Open:

- `http://localhost:8000/ui` — dashboard (decision mix, avg FOIR/CIBIL)
- `http://localhost:8000/ui/queue` — review queue
- `http://localhost:8000/docs` — Swagger API explorer

In Codespaces, use the forwarded port URL (Ports tab) instead of
`localhost`.

## Health checks

- `GET /health` — process is alive
- `GET /health/live` — same as above
- `GET /health/ready` — reports each dependency (`postgresql`, `minio`,
  `opensearch`, `neo4j`, `redis`, `kafka`) as ready/not. **Note**: this
  currently returns hardcoded `True` for all dependencies — it does not yet
  perform live connectivity checks. Treat `/health/ready` as a stub until
  real checks are wired up.

## Running the onboarding pipeline locally

`POST /onboard` (rate-limited to 10/min) accepts a multipart form:
`application` = JSON `LoanApplication`, `documents` = one or more image
files. With `mock_mode=True` (the default everywhere), all ML wrappers and
external API integrations (UIDAI/NSDL/CIBIL/Experian/DigiLocker) return
deterministic mock responses — no network calls are made and no credentials
are required.

## MLOps: drift alerts and retraining

`MLOpsProcessor` (in-memory in mock mode) tracks model registrations, drift
alerts, and retraining triggers. Via `/admin`:

1. `GET /admin/drift-alerts` — list alerts (filter `?acknowledged=false` for
   unactioned ones)
2. `POST /admin/drift-alerts/{alert_id}/acknowledge` — mark as handled
3. `POST /admin/retraining/{model_name}/trigger` — manually kick off a
   scheduled retraining trigger (in mock mode this just records a
   `RetrainingTrigger`, no actual training occurs)
4. `GET /admin/retraining-triggers` — see trigger history
5. `POST /admin/models/{model_name}/promote` — promote a registered model
   version to `staging`/`production`; fails with a `PromotionGate(passed=False)`
   if the model's metrics don't meet `PROMOTION_GATES` thresholds for that
   model name

## mock_mode flags

Every domain processor and ML model wrapper (`loip/models/*_wrapper.py`,
`loip/domains/*/processor.py`) accepts `mock_mode: bool = True`. In mock
mode:

- No external network calls (UIDAI/NSDL/CIBIL/Experian/DigiLocker/PEP lists)
- No real ML inference — wrappers return hardcoded/deterministic outputs
- `ComplianceProcessor.mask_pii_in_text` uses regex-based masking

Setting `mock_mode=False` is currently fully implemented for:

- `XGBoostWrapper`, `LightGBMWrapper`, `GraphSAGEWrapper` — real tabular/graph
  inference using the checkpoints in `models/checkpoints/`, trained on
  synthetic data via `scripts/training/`. Run under `.venv-ml` (see
  `docs/SETUP.md`).
- `BGEM3Wrapper` (real `sentence-transformers` embeddings)
- `ComplianceProcessor` (real Presidio-based PII masking, if
  `presidio-analyzer`/`presidio-anonymizer` are installed — falls back to
  regex automatically if not)

`LayoutLMv3Wrapper`, `DonutWrapper`, and `Qwen25VLWrapper` have complete
`mock_mode=False` code paths (OCR+model inference and fine-tuning scripts)
but require `transformers`/`torch` and model weights that have not been
downloaded in this environment — see "Phase B activation" below. Until
activated they fall back to `mock_mode=True` automatically via
`ImportError`.

## Phase B activation (LayoutLMv3 / Donut / Qwen2.5-VL)

These three wrappers are written and ready to run, but model
downloads/execution were deferred — large weights, no GPU on this dev
machine (see `docs/DATA_GUIDANCE_NOTES.md`). To activate:

1. Install vision/LLM deps into `.venv-ml`:

   ```bash
   cd loip
   .venv-ml/bin/pip install torch transformers
   ```

   (On Linux with a GPU you can instead use `.venv-ml/bin/pip install -e
   ".[gpu]"`, which also pulls in `vllm` — skip that on macOS, the wrappers
   only need `torch`+`transformers`.)

2. (Optional) Fine-tune LayoutLMv3 and/or Donut on the 25-document
   annotation sample — calibration/smoke-test only, not the cancelled
   10,500-doc corpus, see `docs/DATA_GUIDANCE_NOTES.md`:

   ```bash
   .venv-ml/bin/python -m scripts.training.finetune_layoutlmv3
   .venv-ml/bin/python -m scripts.training.finetune_donut
   ```

   These save checkpoints to `models/checkpoints/layoutlmv3-finetuned/` and
   `models/checkpoints/donut-finetuned/`. If absent, the wrappers fall back
   to the zero-shot `microsoft/layoutlmv3-base` / `naver-clova-ix/donut-base`
   checkpoints (downloaded from HuggingFace on first use).

3. Construct the wrappers with `mock_mode=False` (e.g.
   `LayoutLMv3Wrapper(mock_mode=False)`, `Qwen25VLWrapper(mock_mode=False)`).
   `Qwen2_5_VLForConditionalGeneration` (`Qwen/Qwen2.5-VL-3B-Instruct` by
   default) downloads from HuggingFace on first construction.

4. (Optional) Evaluate Qwen2.5-VL field extraction against a DocVQA-style QA
   set via the ANLS gate (`ANLS_GATE_THRESHOLD` in
   `loip/domains/document_intel/schemas.py`):

   ```bash
   .venv-ml/bin/python -m scripts.evaluate_qwen_docvqa --qa-file <path/to/qa.json>
   ```

   The ANLS math itself is unit-tested with synthetic QA pairs
   (`tests/models/test_evaluate_qwen_docvqa.py`); running `main()` against a
   real DocVQA holdout requires a `qa.json` built from a downloaded DocVQA
   dataset, which was not obtained (see `docs/DATA_GUIDANCE_NOTES.md`).

## PaddleOCR annotation pipeline

The annotation pipeline (`scripts/annotate/generate_annotations.py`) runs
in the separate `.venv-ocr` (Python 3.11) venv:

```bash
cd loip
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True .venv-ocr/bin/python -m scripts.annotate.generate_annotations \
  -i data/annotation_corpus/<doc_type> -o data/annotations/<doc_type>
```

PaddleOCR caches model weights under `~/.paddlex/official_models/` on first
run — subsequent runs use the cache. If annotation output looks empty or
mismatched, check:

- The image filename pattern matches `{doc_type}_front_{doc_id}.png` for
  aadhaar (front image has the matchable fields; back image only has QR +
  Aadhaar number).
- PaddleOCR 3.x `.predict()` API (not `.ocr()`) — see
  `_init_ocr`/`annotate_document` in `generate_annotations.py`.

## Common failure modes

- **`ModuleNotFoundError: No module named 'loip'`**: run from the `loip/`
  directory with `PYTHONPATH=.` (the package isn't installed in editable
  mode by default in this environment).
- **`429 Too Many Requests`**: rate limit exceeded — 100/min default,
  10/min on `POST /onboard`. Wait or use a different `X-API-Key`.
- **Presidio ImportError on `ComplianceProcessor(mock_mode=False)`**: falls
  back to regex masking automatically and logs a warning — install
  `presidio-analyzer`/`presidio-anonymizer` (and a spaCy model, e.g.
  `en_core_web_sm`) for full NLP-based PII detection (PERSON/LOCATION).
