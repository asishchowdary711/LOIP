# LOIP — Loan Onboarding Intelligence Platform

**An end-to-end AI-powered personal loan onboarding system for the Indian market.**

LOIP ingests identity documents (PAN, Aadhaar, salary slips, bank statements, ITR, GST returns), verifies applicant identity, reconciles income from multiple sources, assesses affordability, detects fraud, and produces an explainable approve/review/reject decision — all within a single async pipeline backed by 11 ML model wrappers and 13 domain processors.

The platform ships with two frontends: a **Python/Jinja2 demo UI** for the full onboarding pipeline (webcam liveness, document upload, real-time decisioning) and a **React + Express analytics portal** (customer portal, admin console, analytics dashboard, dev sandbox).

> **Honest status (read this first)**: This is a credible technical proof-of-concept demonstrating the ML capabilities of every required stage. It is **not yet a deployable production system** — external bureau APIs (CIBIL/UIDAI/NSDL/DigiLocker) have no real endpoints and stay mocked, and the production `POST /onboard` route still runs in mock mode. The route that runs real ML end-to-end is `POST /apply/submit` (the demo UI). See [What Runs Real vs What's Mocked](#what-runs-real-vs-whats-mocked) and [What's Not Yet Production-Grade](#whats-not-yet-production-grade) for the unvarnished breakdown.

---

## Architecture at a Glance

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Web Layer                                    │
│                                                                      │
│  Python/FastAPI (:8000)                 React + Express (:3000/:5000)│
│  ├── /apply    (Demo UI — REAL ML)      ├── Customer Portal          │
│  ├── /onboard  (Pipeline API — MOCK)    ├── Admin Portal             │
│  ├── /ui       (Admin Review Queue)     ├── Analytics Dashboard      │
│  ├── /vcip     (V-KYC Video)            ├── Auth Portal              │
│  ├── /evidence (Traceability)           └── Dev Sandbox              │
│  └── /docs     (OpenAPI)                                             │
└────────────┬─────────────────────────────────────┬───────────────────┘
             │                                     │
             ▼                                     ▼
┌───────────────────────────────────┐  ┌────────────────────────────────┐
│      OnboardingPipeline           │  │   Express Processing Engine    │
│  13 domain processors with        │  │  14 engines (OCR, classifier,  │
│  evidence chains.                 │  │  identity, fraud, risk, etc.)  │
│  /apply/submit ⇒ real_mode        │  └────────────────────────────────┘
│  /onboard      ⇒ mock_mode        │
└──┬───────┬───────┬───────┬───────┬┘
   │       │       │       │       │
   ▼       ▼       ▼       ▼       ▼
 Doc     QR     Identity Income  Fraud
 Intel   Trust  Trust   Intel    Intel       ┌─────────────────────────────┐
   │       │      │       │       │          │   Infrastructure (Docker)   │
   ▼       ▼      ▼       ▼       ▼          │  Postgres · MinIO · Kafka   │
 Qwen2.5 pyzbar BGE-M3  XGBoost GraphSAGE    │  Neo4j · Redis · MLflow     │
 LayoutLM RSA-  ArcFace LightGBM             │  Prometheus · Grafana       │
 Donut    2048  InsightFace                  │  OpenSearch · Ollama        │
                MiniFASNet                   │                             │
                                             │  → Local FS fallback for    │
                                             │    MinIO when not running   │
                                             └─────────────────────────────┘

  Override gate (demo route only):
  typed values  ──┐
                  ├──► _cross_check  ──► PAN / Aadhaar / Name / Income mismatches
  extracted_fields┘                      downgrade APPROVE → REVIEW
```

## What Runs Real vs What's Mocked

The single source of truth — keep this table honest, don't over-promise.

### Real ML inference (`/apply/submit` with `LOIP_DEMO_REAL_MODELS=1`)

| Stage | Model | Backend | Notes |
|---|---|---|---|
| Document classification | LayoutLMv3 (`microsoft/layoutlmv3-base`) | HuggingFace transformers | Falls back to `BASE_MODEL` on HF when local fine-tuned safetensors absent (the file is gitignored — see [Large Weights](#large-ml-weights)). |
| Document field extraction | Qwen2.5-VL 3B (`qwen2.5vl:3b`) | Ollama (Metal on Apple Silicon) | Default backend. Set `LOIP_QWEN_BACKEND=hf` for HuggingFace transformers (slower on CPU). |
| Secondary extraction (fallback) | Donut (`naver-clova-ix/donut-base`) | HuggingFace transformers | Used when Qwen confidence is low. |
| Primary OCR | PaddleOCR | PaddlePaddle | **Falls back to mock on Python 3.14** — no `paddlepaddle` wheel for 3.14. Surya covers OCR in that case. |
| Secondary OCR | Surya | `surya-ocr` | Always real. |
| Semantic name matching | BGE-M3 (`BAAI/bge-m3`) | `sentence-transformers` | Three independent comparisons: PAN↔app, Aadhaar↔app, PAN↔Aadhaar. Threshold 0.85. |
| Face match | ArcFace (InsightFace `buffalo_l`) | `insightface` + onnxruntime | Selfie vs document face. |
| Liveness (browser challenge) | InsightFace `buffalo_l` | `insightface` | Real-time yaw + eye-aspect-ratio for the 3-step challenge (turn right, turn left, blink). |
| Liveness (still-frame sanity) | MiniFASNet heuristic | InsightFace pose + EAR proxy | Borderline scores route to **review-level fraud signal (0.55)**, not hard reject (0.9). |
| Income / risk scoring | XGBoost | `xgboost` (requires `libomp.dylib` on macOS) | Real checkpoint at `loip/models/checkpoints/xgboost_*.json`. |
| Affordability scoring | LightGBM | `lightgbm` | Real checkpoint. |
| Graph fraud anomaly | GraphSAGE | `scikit-learn`-based, in-memory graph | Deduplicates by `(pan, aadhaar)` so a re-submission isn't a self-match. Reset endpoint: `POST /apply/_reset_fraud_graph`. |
| Explainability | SHAP + LIME | `shap`, `lime` | Per-feature attribution + token-level. |
| Reviewer narrative | Qwen3 (via Ollama) | Ollama | Human-readable decision narrative. |

### Forced mock (no real endpoints configured in this codebase)

| External client | Why | Effect |
|---|---|---|
| CIBIL bureau (`cibil_client.py`) | No live bureau credentials | Score derived deterministically from application_id hash (typically 750). |
| UIDAI Aadhaar OTP (`uidai_client.py`) | No live UIDAI access | `matched=True` returned deterministically. |
| NSDL PAN status (`nsdl_client.py`) | No live NSDL access | Same. |
| DigiLocker | Not integrated | N/A. |

The `_get_pipeline(real_active=True)` builder in `loip/web/routes/demo.py` explicitly sets `_mock = True` on each of these clients **even when the rest of the pipeline is in real mode** — there are no endpoints to call, and pretending otherwise would be dishonest.

### Degraded / optional in dev (no Docker)

| Component | Fallback |
|---|---|
| MinIO | `LocalDocumentStore` at `~/.loip/documents/` — same `bucket/uuid.ext` id format, so evidence chains stay populated. |
| Kafka | Events silently dropped with a startup warning. |
| Neo4j | Identity-graph fraud-ring detection skipped; GraphSAGE still runs against its in-memory node set. |
| PostgreSQL | Demo applications stored as JSON under `loip/data/demo_applications/`. |

## Quick Start

### One-Command Demo

The wrapper script boots venv, deps, models, and the backend:

```bash
./start-demo-real.sh
```

> **Caveat**: the script registers `trap cleanup INT TERM EXIT` and kills its child uvicorn when its parent shell exits. If you're spawning it from a one-shot shell (`nohup bash start-demo-real.sh &`), the EXIT trap fires anyway and takes the server down. For background launches use the direct uvicorn invocation below.

### Recommended: Detached Direct Launch

When you want the server to outlive the spawning shell (background jobs, CI, automation):

```bash
cd /path/to/LOIP

# 1. Ensure Ollama is running and the Qwen model is pulled
ollama serve > /tmp/loip_ollama.log 2>&1 &
ollama pull qwen2.5vl:3b

# 2. Start uvicorn detached, no script wrapper
nohup env \
  PYTHONPATH=$(pwd) \
  PYTHONUNBUFFERED=1 \
  LOIP_DEMO_REAL_MODELS=1 \
  LOIP_OLLAMA_HOST="http://127.0.0.1:11434" \
  LOIP_QWEN_OLLAMA_MODEL="qwen2.5vl:3b" \
  LOIP_QWEN_BACKEND=ollama \
  LOIP_OLLAMA_MAX_CONCURRENCY=2 \
  loip/.venv/bin/uvicorn loip.web.api:app \
    --host 0.0.0.0 --port 8000 --log-level info --access-log \
  > /tmp/loip_demo.log 2>&1 &
disown
```

Then open:

| Screen | URL | Description |
|---|---|---|
| Landing page | http://localhost:8000/ | Entry point — links to customer application and admin console |
| Loan application | http://localhost:8000/apply | Full demo: form → liveness → doc upload → processing → decision (real ML) |
| Admin review queue | http://localhost:8000/ui | Bank-side case review, approve/reject, override workflow |
| React portal | http://localhost:3000/ | Customer portal, admin portal, analytics, dev sandbox |
| API docs | http://localhost:8000/docs | OpenAPI/Swagger interactive documentation |

### Prerequisites

- **Python 3.11+** (3.11 / 3.12 / 3.13 / 3.14 all supported; on **Python 3.14 PaddleOCR falls back to mock** because no `paddlepaddle` wheel exists yet for 3.14 — Surya covers OCR transparently).
- Node.js 18+ and npm (for the React frontend)
- Docker & Docker Compose (optional — needed only for MinIO/Kafka/Neo4j/Postgres; LOIP degrades gracefully without them).
- A webcam (for the in-browser liveness challenge on the demo UI).
- [Ollama](https://ollama.ai/) — required for the Qwen2.5-VL real document extraction path.

### macOS-specific setup notes

- **`libomp.dylib` for xgboost** — `xgboost-py` on macOS arm64 dynamically links against OpenMP. If `brew install libomp` is unavailable (e.g. Homebrew permissions are locked), you can copy the bundled one from sklearn:
  ```bash
  cp loip/.venv/lib/python3.X/site-packages/sklearn/.dylibs/libomp.dylib /opt/homebrew/lib/libomp.dylib
  ```
- **Homebrew permissions** — `chmod u+w /opt/homebrew/...` works without sudo if your user is in the `admin` group.

### Manual Setup

#### 1. Start Infrastructure (Optional)

```bash
cd loip
docker compose up -d
```

This starts: PostgreSQL 16, MinIO, Kafka + Zookeeper, Neo4j 5, OpenSearch, Redis 7, MLflow, Prometheus, Grafana, and Ollama.

If you skip this step, LOIP automatically falls back to the local-filesystem document store (`~/.loip/documents/`), drops Kafka events, and skips Neo4j-backed fraud-ring detection. Real ML still runs.

#### 2. Install Python Dependencies

```bash
cd loip
python3.11 -m venv .venv          # or python3.12 / python3.14 — see Prerequisites
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"

# For webcam liveness, real-mode BGE-M3, sklearn-based fraud, etc.
pip install insightface onnxruntime sentence-transformers accelerate xgboost lightgbm scikit-learn
```

> **QR Trust dependencies** — pyzbar needs `libzbar`:
> ```bash
> brew install zbar          # macOS
> sudo apt-get install libzbar0   # Debian / Ubuntu
> ```

#### 3. Run Database Migrations (only if you started Postgres)

```bash
cd loip
alembic upgrade head
```

#### 4. Start the Backend

```bash
# Mock mode (default — no ML weights needed, fast, CI-safe)
PYTHONPATH=. uvicorn loip.web.api:app --reload --host 0.0.0.0 --port 8000

# Real document extraction + real downstream ML (recommended)
LOIP_DEMO_REAL_MODELS=1 LOIP_OLLAMA_MAX_CONCURRENCY=2 \
  PYTHONPATH=. uvicorn loip.web.api:app --reload --host 0.0.0.0 --port 8000
```

#### 5. Start the React Frontend

```bash
cd frontend && npm install && npm run dev
```

#### 6. Start the Express Backend (for React portal)

```bash
cd backend && npm install && npm run dev
```

### Enable Real Document Verification

```bash
brew install ollama          # macOS
ollama serve &
ollama pull qwen2.5vl:3b     # ~3 GB one-time download

LOIP_DEMO_REAL_MODELS=1 LOIP_OLLAMA_MAX_CONCURRENCY=2 \
  PYTHONPATH=. uvicorn loip.web.api:app --reload --port 8000
```

When `LOIP_DEMO_REAL_MODELS=1` and Ollama is reachable, the demo route (`/apply/submit`) constructs a pipeline with real ML across every domain processor. External bureau/identity clients (CIBIL, NSDL, UIDAI, DigiLocker) stay mocked because no real endpoints are configured.

> **Why 7B is not the answer** — `qwen2.5vl:7b` is larger and **slower**, not faster. The accuracy gain on standard ID/pay-slip layouts doesn't justify the ~2× per-doc latency increase. If 3B is misreading a specific layout, prefer prompt tuning (see [`_DOC_HINTS`](loip/models/qwen2_5_vl_wrapper.py)) over a bigger backbone.

## Demo UI Walkthrough

The demo at **http://localhost:8000/apply** presents the full customer loan application flow:

1. **Applicant Form** — name, mobile, PAN, Aadhaar, employment type, monthly income, loan amount.
2. **Webcam Liveness Challenge** — InsightFace `buffalo_l` powers a real-time 3-step challenge:
   - Turn your head **right** (yaw < −18°)
   - Turn your head **left** (yaw > +18°)
   - **Blink** (eye aspect ratio drops below threshold)
   - Each step must complete in sequence; submit is disabled until all 3 pass.
3. **Document Upload** — 4 slots (Aadhaar, PAN, salary slip, bank statement); images or PDFs.
4. **Processing Animation** — per-document pipeline (Uploading → OCR → Extracting → Validating). Documents now process in **parallel** (gated by `LOIP_OLLAMA_MAX_CONCURRENCY`).
5. **Decision Panel** — real-time approve/review/reject with risk score, fraud-score callout, and explicit mismatch reasons.
6. **Application Tracking** — status page at `/apply/status/{application_id}`.

Applications are stored as JSON in `loip/data/demo_applications/` (no database required). Submitted cases automatically appear in the admin review queue at `/ui`.

## Override Gates — Typed vs Extracted

Even when the ML pipeline lands on APPROVE, a typed-vs-extracted mismatch downgrades it to **REVIEW**. These gates run in [`loip/web/routes/demo.py::_cross_check`](loip/web/routes/demo.py):

| Gate | Compares | Fires when |
|---|---|---|
| **PAN number** | typed `pan_number` vs Qwen-extracted `pan_number` (with OCR fallback) | Case/whitespace-normalised values differ |
| **Aadhaar number** | typed `aadhaar_number` vs Qwen-extracted (plus Verhoeff checksum) | Numbers differ or Verhoeff fails |
| **Name presence** | typed `full_name`'s longest token vs concatenated OCR text AND Qwen-extracted name fields (`full_name`, `employee_name`, `account_holder_name`, `fathers_name`) | Token not found anywhere. *Falls back to structured fields because PaddleOCR's raw text is unreliable on Python 3.14.* |
| **Income variance** | typed `monthly_income` vs salary slip `net_pay` AND bank statement average salary credit | Delta exceeds **±10%** |

A failure on any of these is appended to `decision.review_flags` and forces APPROVE → REVIEW.

## Income Reconciliation

The income processor (`loip/domains/income_intel/processor.py`) reconciles across documents with source-trust weighting, then validates against the applicant's typed declaration.

### Source-trust weights (salaried vs self-employed)

| Source | Weight (salaried) | Weight (self-employed) |
|---|---|---|
| ITR — current FY | 0.85 | 0.90 |
| ITR — prior FY (2-yr avg) | 0.80 | 0.80 |
| GST returns | — | 0.75 (turnover × 25% margin) |
| Bank statement avg salary credit | 0.75 | 0.65 |
| Salary slip net pay | 0.65 | — |

### Bank statement parsing — credits only

Qwen is now prompted to return `salary_credits` as a JSON array of **credit-direction** transactions only. A backend filter further excludes anything whose narration matches `emi / loan / repayment / transfer out / atm / pos / charges / gst / interest debit / bill pay / dr ` (the **belt-and-braces** layer), so an EMI debit can't be mis-classified into the income reconciliation.

### Anomaly flags

| Flag | Trigger |
|---|---|
| `INCOME_DECLARATION_MISMATCH` | |typed − verified| / max > 10% |
| `INCOME_INFLATION` | Typed > verified by >10% |
| `INCOME_DEFLATION` | Typed < verified by >10% |
| `SALARY_SLIP_VS_BANK_MISMATCH` | Slip net_pay vs bank avg credit diverge >30% |
| `NO_SALARY_CREDIT_FOUND` | Bank statement has no credit-direction transactions (salaried segment only) — hard reject signal |
| `INCOME_BELOW_RBI_MINIMUM` | Verified monthly income < ₹20,000 |
| `EMPLOYER_NAME_MISMATCH` | Slip employer ≠ application-declared employer |

The pipeline replaced an earlier mock-mode-only behaviour where a missing `salary_credits` array would fabricate a synthetic credit equal to the salary slip net_pay (silently passing the slip-vs-bank check). In real mode that fallback is now suppressed.

## Speed Optimisations

Per-document Qwen latency was ~25 s; 4 docs serial ~100 s. After these landed:

| Change | Where | Effect |
|---|---|---|
| Image downscaled to **1280-px longest edge, JPEG q=85** before being sent to Ollama | [`qwen2_5_vl_wrapper.py::_prepare_image`](loip/models/qwen2_5_vl_wrapper.py) | 2–4× per doc (fewer vision tokens) |
| Ollama `options.num_ctx=2048`, `options.num_predict=512`, `keep_alive="10m"` | Qwen wrapper Ollama payload | 1.2–1.5× per doc; model stays warm between requests |
| Per-document processing in parallel via `asyncio.to_thread` + `asyncio.gather` | [`pipelines/onboarding.py`](loip/pipelines/onboarding.py) and `web/routes/demo.py::_extract_fields_by_class` | Linear speedup in # docs |
| Bounded Ollama concurrency (`threading.Semaphore`) — too many concurrent requests caused HTTP 500s | Qwen wrapper `_OLLAMA_SEMAPHORE` | Avoids floods on single-GPU laptops |
| HTTP 5xx retry with exponential backoff (1 → 2 → 4 s, 3 attempts) | Qwen wrapper + `document_intel._classify_via_ollama` | Survives transient queue-full responses |

**Knob**: `LOIP_OLLAMA_MAX_CONCURRENCY` (default `2`). Increase if your hardware can serve more concurrent VL requests.

Wall-clock: ~100 s → ~10–15 s for a 4-document submission on Apple Silicon (Metal-accelerated Ollama).

## Traceability & Evidence Chains

Every extracted figure traces back to its source document via `EvidenceChain → ExtractedField → SourceLocation(document_id, document_type, field_name, extraction_method, model_version, confidence)`.

### Document store

- **MinIO** when running (`docker compose up -d minio`).
- **LocalDocumentStore** (`loip/storage.py::LocalDocumentStore`) at `~/.loip/documents/` when MinIO is down. Same id format (`<bucket>/<uuid>.<ext>`) — downstream consumers don't care which backend served it. Override path via `LOIP_LOCAL_DOC_STORE`.

### Retrieval endpoints

| Endpoint | Returns |
|---|---|
| `GET /evidence/{application_id}/chains` | All evidence chains for the decision (identity, income, affordability). |
| `GET /evidence/{application_id}/source/{field_name}` | The single `SourceLocation` that produced a given field. |
| `GET /evidence/document/{bucket}/{uuid}.{ext}` | Streams the raw stored document back (PDF/PNG/JPEG). Auth: `Authorization: Bearer dev-admin-token`. |

`is_synthetic` on a `SourceLocation` reflects whether the source was mock-generated; `model_version` distinguishes `qwen2.5-vl:3b` (real) from `qwen2.5-vl-mock`.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LOIP_DEMO_REAL_MODELS` | `0` | Enable real ML in `/apply/submit`. Auto-detects Ollama reachability when unset. `0` forces mock. |
| `LOIP_QWEN_BACKEND` | `ollama` | Qwen backend: `ollama` or `hf` |
| `LOIP_OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `LOIP_QWEN_OLLAMA_MODEL` | `qwen2.5vl:3b` | Ollama model name for Qwen |
| `LOIP_OLLAMA_MAX_CONCURRENCY` | `2` | Cap on concurrent Qwen requests. Single-GPU laptops should keep this ≤ 2. |
| `LOIP_LOCAL_DOC_STORE` | `~/.loip/documents` | Filesystem path for the LocalDocumentStore fallback. |
| `LOIP_INSIGHTFACE_MODEL` | `buffalo_l` | InsightFace model pack for webcam liveness |
| `UIDAI_PUBLIC_KEY_PATH` | `loip/keys/uidai_public_key.pem` | UIDAI RSA-2048 public key for Aadhaar QR signature verification |
| `QR_NAME_SIMILARITY_THRESHOLD` | `0.80` | Minimum name similarity score (QR vs OCR) |
| `QR_ADDRESS_SIMILARITY_THRESHOLD` | `0.70` | Minimum address similarity score (QR vs OCR) |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Database connection string |
| `PORT` | `5000` | Express backend port |

## Project Structure

```
LOIP/
├── loip/                           # Python backend
│   ├── domains/
│   │   ├── document_intel/         #   LayoutLMv3 + PaddleOCR + Surya + Qwen2.5-VL + Donut
│   │   ├── qr_trust/               #   pyzbar/OpenCV, UIDAI RSA, ELA+EXIF
│   │   ├── identity_trust/         #   PAN/Aadhaar verification, 3× BGE-M3, face match
│   │   ├── income_intel/           #   Multi-source reconciliation + declared-vs-verified ±10%
│   │   ├── affordability/          #   EMI, FOIR, disposable income (LightGBM)
│   │   ├── fraud/                  #   GraphSAGE anomaly + soft liveness routing
│   │   ├── risk_decisioning/       #   Rule gates + XGBoost ensemble
│   │   ├── explainability/         #   SHAP + LIME + Qwen3 copilot
│   │   ├── human_review/           #   Review queue, case assignment, overrides
│   │   ├── compliance/             #   DPDP consent, PII masking, KFS, AML
│   │   ├── truth_reconciliation/   #   Cross-source field reconciliation
│   │   ├── mlops/                  #   Model registry, drift monitoring
│   │   └── evidence/               #   Evidence chain schemas
│   ├── models/                     # 11 ML model wrappers (mock + real backends)
│   │   ├── qwen2_5_vl_wrapper.py   #   With _prepare_image, semaphore, retry-on-500
│   │   ├── graphsage_wrapper.py    #   Dedup by (pan, aadhaar), reset_graph()
│   │   ├── layoutlmv3_wrapper.py   #   Falls back to BASE_MODEL if local weights absent
│   │   ├── minifasnet_wrapper.py   #   Looser pose tolerance
│   │   └── checkpoints/            #   xgboost_*.json, lightgbm_*.txt, graphsage_*.joblib
│   ├── integrations/               # External API clients (CIBIL, NSDL, UIDAI, DigiLocker) — all forced mock
│   ├── pipelines/
│   │   └── onboarding.py           # Main async orchestration; parallel doc processing
│   ├── storage.py                  # DocumentStore (MinIO) + LocalDocumentStore + open_document_store()
│   ├── web/
│   │   ├── routes/                 # demo, onboard, review, admin, audit, consent, vcip, evidence
│   │   └── templates/apply.html    # Demo UI — override-gate aware
│   ├── docker-compose.yml          # 12 infrastructure services
│   └── pyproject.toml
│
├── frontend/                       # React + Vite SPA (:3000)
├── backend/                        # Express.js API (:5000)
├── start-demo-real.sh              # Wrapper script (see EXIT-trap caveat above)
├── start-demo.sh                   # Mock-mode wrapper
└── .github/workflows/ci.yml
```

## API Documentation

With the server running, visit **http://localhost:8000/docs** for the full OpenAPI spec.

### FastAPI Endpoints (Python Backend — :8000)

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Landing page |
| `/apply` | GET | Demo loan application UI |
| `/apply/submit` | POST | Submit demo application (rate-limited 10/min) — **runs real ML when `LOIP_DEMO_REAL_MODELS=1`** |
| `/apply/liveness` | POST | Webcam frame analysis — returns yaw + EAR for liveness challenge |
| `/apply/liveness/warmup` | GET | Pre-load InsightFace before the first webcam frame |
| `/apply/status/{id}` | GET | Application status page |
| `/apply/mode` | GET | Current mode (`{"real_models": bool, "mode_label": str}`) |
| `/apply/_reset_fraud_graph` | POST | Clear the in-memory GraphSAGE node set — use between demo retests with the same identity |
| `/onboard` | POST | Full onboarding pipeline (API) — **mock_mode hardcoded; not production-real** |
| `/review/queue` | GET | Human review queue |
| `/review/{case_id}` | GET | Review case detail |
| `/review/{case_id}/override` | POST | Submit reviewer override |
| `/evidence/{app_id}/chains` | GET | All evidence chains for a decision |
| `/evidence/{app_id}/source/{field}` | GET | Source location for a specific extracted field |
| `/evidence/document/{document_id:path}` | GET | Stream a stored source document (auth required) |
| `/vcip/initiate` | POST | Start V-CIP video KYC session |
| `/compliance/consent` | POST | Record DPDP consent |
| `/ui` | GET | Admin dashboard |
| `/docs` | GET | OpenAPI/Swagger docs |

### Express Endpoints (Node.js Backend — :5000)

| Endpoint | Method | Description |
|---|---|---|
| `/api/auth/register` | POST | Register new user |
| `/api/auth/login` | POST | Login (returns JWT) |
| `/api/auth/profile` | GET | Get user profile |
| `/api/loans/apply` | POST | Submit loan application with documents |
| `/api/loans` | GET | List user's loans |
| `/api/loans/:id` | GET | Get loan details |
| `/api/admin/applications` | GET | Admin — list all applications |
| `/api/admin/applications/:id/approve` | POST | Admin — approve application |
| `/api/admin/applications/:id/reject` | POST | Admin — reject application |
| `/api/admin/applications/:id/request-docs` | POST | Admin — request additional documents |
| `/api/analytics/*` | GET | Analytics data endpoints |

## Infrastructure Services (Docker Compose)

| Service | Port | Purpose |
|---|---|---|
| PostgreSQL 16 | 5432 | Application decisions, review state, audit log |
| MinIO | 9000/9001 | Document storage (per-type buckets) |
| Kafka + Zookeeper | 9092 | Domain event pipeline (8 topics) |
| Neo4j 5 | 7474/7687 | Identity graph + fraud ring detection |
| OpenSearch | 9200 | Full-text search (planned) |
| Redis 7 | 6379 | Caching (planned) |
| MLflow | 5000 | Model registry + experiment tracking |
| Prometheus | 9090 | Metrics collection |
| Grafana | 3000 | Monitoring dashboards |
| Ollama | 11434 | Local LLM inference (Qwen2.5-VL, Qwen3) |

## ML Models

| Model | Role | Wrapper | Real Backend |
|---|---|---|---|
| Qwen2.5-VL 3B | Primary document field extraction | `qwen2_5_vl_wrapper.py` | Ollama (verified) |
| LayoutLMv3 | Document type classification | `layoutlmv3_wrapper.py` | HuggingFace transformers |
| PaddleOCR | Primary OCR engine | `paddleocr_wrapper.py` | PaddlePaddle (mock on Py 3.14) |
| Surya | Secondary OCR (fallback) | `surya_wrapper.py` | surya-ocr |
| Donut | Secondary structured extraction | `donut_wrapper.py` | HuggingFace transformers |
| BGE-M3 | Name/entity similarity (3 pairs) | `bge_m3_wrapper.py` | sentence-transformers |
| ArcFace (InsightFace `buffalo_l`) | Face verification + webcam liveness | `arcface_wrapper.py` | insightface |
| MiniFASNet | Still-frame liveness sanity (soft signal) | `minifasnet_wrapper.py` | InsightFace pose heuristic |
| XGBoost | Risk scoring + income confidence | `xgboost_wrapper.py` | xgboost (needs `libomp`) |
| LightGBM | Affordability scoring | `lightgbm_wrapper.py` | lightgbm |
| GraphSAGE | Graph fraud anomaly (with identity dedup) | `graphsage_wrapper.py` | scikit-learn |

### Large ML Weights

`loip/models/checkpoints/layoutlmv3-finetuned/model.safetensors` and `donut-finetuned/model.safetensors` are **gitignored** — they exceed GitHub's 100 MB file limit. The wrappers fall back to the public HuggingFace `BASE_MODEL` when the local file is absent or smaller than 1 MB. On a fresh clone the first inference will pull from HuggingFace; subsequent runs use the local HF cache.

## QR Trust Verification

LOIP runs a dedicated QR Trust Verification Module on every uploaded Aadhaar and PAN card after OCR extraction. It adds a cryptographic and visual integrity layer on top of standard field matching.

### How It Works

```
Document Upload (Aadhaar / PAN)
        │
        ▼
QR Presence Detection (pyzbar → OpenCV fallback)
        │
        ├── No QR → Risk flag: QR_NOT_FOUND
        │
        ▼
QR Decoder → QR type classification (Secure QR / Text QR / PAN QR)
        │
        ├── Aadhaar Secure QR ──→ zlib decompress → XML parse → RSA-2048 signature verify
        ├── PAN QR ─────────────→ Base64 decode → pipe-delimited parse → format regex check
        │
        ▼
QR ↔ OCR Cross-Field Validation
   • Name (difflib similarity ≥ 0.80)
   • Date of Birth (exact, normalised for DD/MM/YYYY vs DD-MM-YYYY)
   • Aadhaar UID last 4 digits (exact)
   • PAN number (exact)
   • Address (similarity ≥ 0.70, Aadhaar only)
        │
        ▼
Tampering Detection
   • ELA (Error Level Analysis) — PIL re-save at 75% quality, pixel diff
   • EXIF metadata inspection — editing software keywords, GPS strip, dimension mismatch
   • overall_tampered = ELA anomaly AND EXIF anomaly (both must fire)
        │
        ▼
Trust Score (0.0–1.0) + QRTrustFlag list → merged into IdentityVerificationResult
```

### Trust Signals and Risk Weights

| Signal | Flag | Trust Deduction |
|---|---|---|
| QR not found | `QR_NOT_FOUND` | −0.20 |
| QR decode failed | `QR_DECODE_FAILED` | −0.20 |
| Aadhaar RSA signature invalid | `QR_SIGNATURE_INVALID` | −0.35 |
| Aadhaar RSA signature absent | `QR_SIGNATURE_MISSING` | −0.10 |
| Any field mismatch (name/DOB/number) | `QR_*_MISMATCH` | −0.10 each |
| ELA anomaly alone | `QR_ELA_ANOMALY` | −0.10 |
| EXIF anomaly alone | `QR_EXIF_ANOMALY` | −0.10 |
| Both ELA + EXIF anomaly | `QR_TAMPERED` | −0.30 |

> **UI note**: a high `fraud_score` from GraphSAGE or liveness is **not** the same thing as document tampering. The UI labels the PAN row "Possible tampering" only when an actual identity tamper flag fires (`document_metadata_anomaly`, `qr_tampered`, `qr_signature_invalid`) — not when the reason code contains the substring "fraud".

### Aadhaar Secure QR Signature Verification

UIDAI embeds an RSA-2048 PKCS#1 v1.5 + SHA-256 signature in every Secure QR. To enable real verification:

1. Obtain the official public key from [developer.uidai.gov.in](https://developer.uidai.gov.in)
2. Place it at `loip/keys/uidai_public_key.pem` (or set `UIDAI_PUBLIC_KEY_PATH` env var)

Without the real key, signature verification is disabled with a warning — the pipeline continues with `signature_valid=False` and a `QR_SIGNATURE_MISSING` flag.

### DPDP Act Compliance

- Aadhaar UID is **masked to the last 4 digits** at parse time and never stored or serialized in full
- XML parsing uses `defusedxml` to prevent entity expansion DoS attacks
- The `loip/keys/` directory is in `.gitignore` (except the placeholder stub)

## Fraud Signals

| Signal | Severity | Effect |
|---|---|---|
| GraphSAGE anomaly (graph_fraud_score > 0.8) | `graph_fraud_score` | Hard reject when total fraud_score > 0.80 |
| Passport MRZ checksum invalid (ICAO 9303) | 0.9 | Hard reject |
| Liveness `score < 0.25` | 0.9 | Hard reject |
| Liveness `0.25 ≤ score < 0.50` | **0.55** | Review-level — borderline still-frame liveness no longer auto-rejects |
| Neo4j fraud-ring patterns (when graph available) | per-rule | Surface peers + signal |

GraphSAGE deduplicates by `(pan, aadhaar)` identity tuple. Re-submitting the same documents from the same applicant doesn't accumulate as a self-match — only distinct applications under the same identity count. For clean demo runs without restarting the server, call `POST /apply/_reset_fraud_graph`.

## Demo Gotchas

A short list of operational quirks worth knowing before debugging the demo:

- **Same applicant re-submitting**: GraphSAGE counts each distinct application id under the same `(pan, aadhaar)` once (deduplicated). If you're retesting and want a fully clean slate, call `POST /apply/_reset_fraud_graph` or restart the server.
- **PaddleOCR mock on Python 3.14**: raw OCR text returned as `"MOCK_TEXT"`. The name cross-check falls back to Qwen-extracted structured fields (added in this session), so this doesn't false-flag legitimate submissions.
- **The 5th uploaded image is treated as the selfie** (`images[-1]`). If you skip the live challenge the bank statement becomes the "selfie" and liveness fails — start fresh and complete the 3-step challenge.
- **Ollama HTTP 500 floods**: 5+ concurrent VL requests overwhelm Ollama on a single GPU. Default `LOIP_OLLAMA_MAX_CONCURRENCY=2` solves it, with retry-on-5xx for transient failures.
- **start-demo-real.sh kills uvicorn when its parent shell exits** (EXIT trap). Use the [Detached Direct Launch](#recommended-detached-direct-launch) recipe for background runs.

## Regulatory Compliance

- **RBI Digital Lending Guidelines**: Key Fact Statement (KFS) generation, cooling-off period, NACH mandate.
- **DPDP Act 2023**: Consent management, data deletion, PII masking (Presidio + regex fallback).
- **PMLA / AML**: PEP screening, AML risk assessment, SAR flagging.
- **RBI V-CIP**: Video KYC lifecycle with geotag, OVD presentation, random questions, recording storage.
- **Data Residency**: India-region enforcement check for all service endpoints.

> Compliance scaffolding is in place but **not production-grade**: no immutable audit ledger, no auditor view, no enforced data-retention policy, and consent receipts aren't cryptographically anchored. Treat the compliance domain as a wireframe of the workflow, not a regulator-ready system.

## What's Not Yet Production-Grade

Honest scope of remaining work — pasted here so it doesn't get lost in roadmap docs:

1. **External bureau/identity integrations are mocked.** CIBIL/UIDAI/NSDL/DigiLocker have no real endpoints. A production deployment would need credentials + integration + idempotency for each.
2. **The `POST /onboard` route still runs `mock_mode=True`.** Only `/apply/submit` constructs the real-ML pipeline. Productionising the generic route means lifting `_get_pipeline(real_active=True)`'s logic out of the demo route and into the API path with proper auth + rate-limit + audit.
3. **Tamper detection is shallow.** ELA + EXIF + Photoshop-string detection is defeated by anyone who flattens the image in another editor. No deepfake detection, no font-consistency checks, no PDF signature verification (Form 16 / ITRs are cryptographically signed by ITD; we treat them as images).
4. **No real employer verification.** The pipeline trusts whatever Qwen reads as `employer_name` — no EPFO UAN lookup, no MCA company-registration check, no GSTIN-to-PAN linkage validation.
5. **GraphSAGE runs on an in-memory graph.** Fine for a single-process demo; production needs Neo4j (already in docker-compose) wired into the wrapper as the persistent store.
6. **Latency**. Even with the speed optimisations, a 4-document submission is ~10–15 s wall-clock on Apple Silicon. Production needs GPU batching or a smaller/faster VL model (or an inference proxy).
7. **Audit / compliance scaffolding** — see above.

If you're evaluating LOIP as a starting point for a real lending stack: the ML/CV/NLP layer is honest and re-usable; the integration surface is where most of the operational risk lives and most of the remaining work sits.

## Running Tests

```bash
cd loip
DATABASE_URL=sqlite+aiosqlite:///data/dev.db pytest -q
```

## CI/CD

GitHub Actions runs on every push to `main` and on pull requests:

- **test** job: ruff lint, mypy type check, pytest (with SQLite fallback)
- **security** job: pip-audit, bandit, safety check
- System dependencies (`libzbar0`, `poppler-utils`) are installed automatically in CI

## License

Private repository — all rights reserved.
