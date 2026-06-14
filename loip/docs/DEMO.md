# DEMO GUIDE

A 15–20 minute walkthrough of LOIP (Loan Onboarding Intelligence Platform —
Personal Loans, India). Everything below runs in **mock mode** (no GPU, no
external API keys, no Docker required).

## 0. One-time setup (if not already done)

```bash
cd /workspaces/LOIP/loip
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## 1. Show the build plan (2 min)

Open `LOIP_BUILD_PLAN_v3_PersonalLoans_India.md`. Hit the highlights:
scope (personal loans, India), the 8 domains, the traceability contract
(`EvidenceChain` / `SourceLocation`), and the RBI/DPDP compliance layer.

## 2. Show synthetic document generation (2 min)

Open a couple of pre-generated samples from
`loip/data/annotation_sample25/` — e.g. a PAN card PNG and a salary-slip
PDF. Or generate a fresh case live:

```bash
cd /workspaces/LOIP
PYTHONPATH=/workspaces/LOIP:/workspaces/LOIP/loip \
  loip/.venv/bin/python -m scripts.generators.generate_case \
  --output ./loip/data/demo --segment salaried
```

## 3. Run the pipeline from the CLI (2 min)

```bash
cd /workspaces/LOIP
CASE=$(find ./loip/data/demo -maxdepth 1 -type d -name 'case_*' | head -1)
PYTHONPATH=/workspaces/LOIP:/workspaces/LOIP/loip \
  loip/.venv/bin/python -m loip.evaluate --case-dir "$CASE"
```

Point out: the decision (APPROVE/REVIEW/REJECT), reason codes, FOIR, CIBIL
gate, and evidence-chain count — every figure is traceable to a source.

## 4. Launch the web console (1 min)

```bash
cd /workspaces/LOIP
PYTHONPATH=/workspaces/LOIP loip/.venv/bin/uvicorn loip.web.api:app \
  --host 0.0.0.0 --port 8000
```

The app auto-seeds 7 demo cases. In Codespaces, open the forwarded port
URL from the **Ports** tab.

## 5. Walk the UI (5 min)

- **`/ui` — Dashboard:** decision mix (2 approve / 3 review / 2 reject),
  avg FOIR, avg CIBIL, recent applications table.
- **`/ui/queue` — Review queue:** sorted by risk; columns for FOIR, CIBIL,
  primary reason code, age in queue.
- **`/ui/review/{case_id}` — Case detail:** click any "Review" button.
  - Left: identity / income / affordability / credit-bureau panels, plus
    the **Evidence Chains** card (claim → reconciled value →
    reconciliation method → source document + extraction method).
  - Right: **SHAP risk factors**, **AI copilot** narrative, review flags,
    and the **decision override** form.
- **Submit an override:** pick a decision + reason code + notes → the case
  flips to `completed` and the override is captured for the retraining
  feedback loop.
- **Persistence (optional flourish):** restart the server and reopen
  `/ui/queue` — the queue, decisions, evidence, and your override are still
  there. State lives in Postgres (`docker compose ps`), documents in MinIO
  (console at http://localhost:9001), and `GET /health/ready` shows both
  connected.

## 6. Show the API (2 min)

Open `/docs` (Swagger). Good endpoints to hit live:

- `GET /health`
- `GET /review/queue`
- `GET /evidence/{application_id}/chains` (use an `APP-100x` id)
- `POST /onboard` — multipart: `application` JSON + `documents` files
- `GET /compliance/data-residency` — RBI localization check
- `POST /compliance/kfs/{application_id}` — Key Fact Statement (RBI DLG)

## 7. Show the tests pass (1 min)

```bash
cd /workspaces/LOIP/loip
PYTHONPATH=. .venv/bin/python -m pytest -q
```

With the Docker stack up: **77 passed, 6 skipped** (the MinIO + Postgres
integration tests run for real; the skips require the full 10,500-doc corpus
/ DocVQA weights / `.venv-ml` — see `docs/DATA_GUIDANCE_NOTES.md`). Without
Docker the integration tests skip instead, so the suite still passes.

## What to frame as "future phases" (don't demo)

- Real OCR/VLM inference (LayoutLMv3 / Donut / Qwen2.5-VL) — wrappers exist,
  weights deferred (`docs/RUNBOOK.md` → "Phase B activation").
- Heavier compose services (Neo4j, Kafka, OpenSearch, MLflow, Grafana,
  Ollama) — defined in `docker-compose.yml` but not yet in the request path
  (Postgres + MinIO are wired and persistent).
- Face verification / liveness / V-KYC — Phase 2 stubs.

> If a real LLM key is ever needed (e.g. running the Qwen3 copilot with
> `mock_mode=False`), source it from OpenRouter or Bytez and set it in
> `.env`. The demo path does **not** need one.
