# LOIP — Loan Onboarding Intelligence Platform

**An end-to-end AI-powered personal loan onboarding system for the Indian market.**

LOIP ingests identity documents (PAN, Aadhaar, salary slips, bank statements, ITR, GST returns), verifies applicant identity against government databases (NSDL, UIDAI), reconciles income from multiple sources, assesses affordability, detects fraud through graph analysis, and produces an explainable approve/review/reject decision — all within a single async pipeline backed by 11 ML model wrappers and 13 domain processors.

The platform ships with two frontends: a **Python/Jinja2 demo UI** for the full onboarding pipeline (webcam liveness, document upload, real-time decisioning) and a **React + Express analytics portal** (customer portal, admin console, analytics dashboard, dev sandbox).

Built for RBI Digital Lending Guidelines, DPDP Act 2023 compliance, and PMLA/AML screening.

---

## Architecture at a Glance

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Web Layer                                    │
│                                                                      │
│  Python/FastAPI (:8000)                 React + Express (:3000/:5000)│
│  ├── /apply    (Demo UI)                ├── Customer Portal          │
│  ├── /onboard  (Pipeline API)           ├── Admin Portal             │
│  ├── /ui       (Admin Review Queue)     ├── Analytics Dashboard      │
│  ├── /vcip     (V-KYC Video)            ├── Auth Portal              │
│  └── /docs     (OpenAPI)                └── Dev Sandbox              │
└────────────┬──────────────────────────────────────┬──────────────────┘
             │                                      │
             ▼                                      ▼
┌─────────────────────────────────┐   ┌────────────────────────────────┐
│      OnboardingPipeline         │   │   Express Processing Engine    │
│  13 domain processors with      │   │  14 engines (OCR, classifier,  │
│  evidence chains + mock_mode    │   │  identity, fraud, risk, etc.)  │
└──┬──────┬──────┬──────┬──────┬──┘   └────────────────────────────────┘
   │      │      │      │      │
   ▼      ▼      ▼      ▼      ▼
 Doc    QR     Identity Income Fraud    ┌─────────────────────────────┐
 Intel  Trust  Trust    Intel  Intel    │   Infrastructure (Docker)   │
   │      │      │        │      │      │  Postgres · MinIO · Kafka   │
   ▼      ▼      ▼        ▼      ▼      │  Neo4j · Redis · MLflow     │
 5 ML  pyzbar  BGE-M3  XGBoost Graph-  │  Prometheus · Grafana       │
 models OpenCV  ArcFace        SAGE    │  OpenSearch · Ollama        │
        UIDAI   MiniFAS        Neo4j   └─────────────────────────────┘
        RSA-2048
```

## Key Features

| Feature | Status | Description |
|---------|--------|-------------|
| **Document Intelligence** | Working | LayoutLMv3 classification → PaddleOCR + Surya dual-OCR → Qwen2.5-VL + Donut extraction |
| **Real Document Verification** | Working | Ollama backend for Qwen2.5-VL (`qwen2.5vl:3b`) — genuinely reads uploaded documents |
| **QR Trust Verification** | Working | pyzbar + OpenCV QR decode → UIDAI RSA-2048 signature verification → QR↔OCR cross-check → ELA + EXIF tampering detection |
| **Identity Trust** | Working | PAN/NSDL verification, Aadhaar Verhoeff checksum, ArcFace face matching, MiniFASNet liveness |
| **Income Intelligence** | Working | Multi-source reconciliation (salary slip, bank statement, ITR, GST) with source-trust weighting |
| **Affordability Assessment** | Working | EMI calculation, FOIR analysis, disposable income, LightGBM scoring |
| **Fraud Detection** | Working | Neo4j graph fraud rings (PAN farming, synthetic identity, address rings) + GraphSAGE anomaly |
| **Risk Decisioning** | Working | Rule-based hard gates + XGBoost ensemble scoring + V-CIP regulatory gate |
| **Explainability** | Working | SHAP waterfall + LIME token attribution + Qwen3 reviewer copilot narrative |
| **Human Review Queue** | Working | Full queue management, case assignment, override workflow, retraining data export |
| **Evidence Traceability** | Working | Every decision field traces to a source document via evidence chains |
| **V-CIP Video KYC** | Working | RBI-compliant video KYC lifecycle (geotag, OVD, random questions, recording) |
| **Compliance** | Working | DPDP consent management, PII masking, KFS generation, cooling-off period, AML screening |
| **MLOps** | Working | Model registry, promotion gates, drift monitoring, retraining triggers |
| **Demo UI** | Working | Customer-facing loan application at `/apply` with animated processing |
| **Webcam Liveness Gate** | Working | InsightFace-powered 3-step challenge (turn right → turn left → blink) gates the submit button |
| **PDF Document Upload** | Working | Upload PDFs directly; backend converts pages via PyMuPDF before OCR |
| **Analytics Portal** | Working | React + Express dashboard with loan analytics, processing metrics, and report centre |
| **Customer Portal** | Working | React SPA — apply for loans, upload documents, track status in real time via SSE |
| **Admin Portal** | Working | React SPA — review applications, approve/reject, request additional docs, bureau & risk drill-down |
| **Auth System** | Working | JWT-based authentication with role separation (user / admin) |
| **Dev Sandbox** | Working | React component for testing individual processing engines in isolation |

## Quick Start

### One-Command Demo

The fastest way to boot the full demo with all dependencies:

```bash
./start-demo.sh
```

This single command:
1. Creates/reuses a Python virtual environment at `loip/.venv`
2. Installs all Python dependencies (including InsightFace for webcam liveness)
3. Installs frontend npm dependencies
4. Kills any stale server processes
5. Starts the FastAPI backend on **:8000**
6. Starts the React frontend on **:3000**
7. Waits for startup and prints all URLs
8. `Ctrl+C` stops both servers cleanly

Once running, open:

| Screen | URL | Description |
|--------|-----|-------------|
| Landing page | http://localhost:8000/ | Entry point — links to customer application and admin console |
| Loan application | http://localhost:8000/apply | Full demo: form → liveness → doc upload → processing → decision |
| Admin review queue | http://localhost:8000/ui | Bank-side case review, approve/reject, override workflow |
| React portal | http://localhost:3000/ | Customer portal, admin portal, analytics, dev sandbox |
| API docs | http://localhost:8000/docs | OpenAPI/Swagger interactive documentation |

### Prerequisites

- Python 3.11+
- Node.js 18+ and npm (for the React frontend)
- Docker & Docker Compose (for infrastructure services — optional for demo)
- A webcam (for the in-browser liveness challenge on the demo UI)
- [Ollama](https://ollama.ai/) (optional, for real document extraction)

### Manual Setup (if not using start-demo.sh)

#### 1. Start Infrastructure (Optional)

```bash
cd loip
docker compose up -d
```

This starts: PostgreSQL 16, MinIO, Kafka + Zookeeper, Neo4j 5, OpenSearch, Redis 7, MLflow, Prometheus, Grafana, and Ollama.

#### 2. Install Python Dependencies

```bash
cd loip
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# For webcam liveness detection
pip install insightface onnxruntime
```

> **QR Trust dependencies** — pyzbar requires the `libzbar` system library:
> ```bash
> # macOS
> brew install zbar
> # Debian / Ubuntu
> sudo apt-get install libzbar0
> # Docker — add before pip install in your RUN layer
> ```

#### 3. Run Database Migrations

```bash
cd loip
alembic upgrade head
```

#### 4. Start the Backend

```bash
# Mock mode (default — no ML weights needed, fast, CI-safe)
PYTHONPATH=. uvicorn loip.web.api:app --reload --host 0.0.0.0 --port 8000

# With real document extraction (requires Ollama + qwen2.5vl:3b)
LOIP_DEMO_REAL_MODELS=1 PYTHONPATH=. uvicorn loip.web.api:app --reload --host 0.0.0.0 --port 8000
```

#### 5. Start the React Frontend

```bash
cd frontend
npm install
npm run dev
```

#### 6. Start the Express Backend (for React portal)

```bash
cd backend
npm install
npm run dev
```

### Enable Real Document Verification (Optional)

```bash
# Install and start Ollama
brew install ollama  # macOS
ollama serve &

# Pull the Qwen2.5-VL model (3.2 GB)
ollama pull qwen2.5vl:3b

# Start with real models
LOIP_DEMO_REAL_MODELS=1 PYTHONPATH=. uvicorn loip.web.api:app --reload --port 8000
```

When `LOIP_DEMO_REAL_MODELS=1` is set, document extraction uses the real Qwen2.5-VL model via Ollama while keeping external API clients (CIBIL, NSDL, UIDAI) in mock mode.

## Demo UI Walkthrough

The demo at **http://localhost:8000/apply** presents the full customer loan application flow:

1. **Applicant Form** — 7 fields: name, mobile, PAN, Aadhaar, employment type, monthly income, loan amount
2. **Webcam Liveness Challenge** — InsightFace `buffalo_l` model powers a real-time 3-step challenge:
   - Turn your head **right** (yaw < −18°)
   - Turn your head **left** (yaw > +18°)
   - **Blink** your eyes (eye aspect ratio drops below threshold)
   - Each step must be completed in sequence; submit is disabled until all 3 pass
3. **Document Upload** — 4 slots (Aadhaar, PAN, salary slip, bank statement); supports images and PDFs
4. **Processing Animation** — animated 4-stage per-document pipeline (Uploading → OCR → Extracting → Validating)
5. **Decision Banner** — real-time approve/review/reject result with confidence score
6. **Application Tracking** — status page at `/apply/status/{application_id}`

Applications are stored as JSON in `loip/data/demo_applications/` (no database required for demo). Submitted cases automatically appear in the admin review queue at `/ui`.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOIP_DEMO_REAL_MODELS` | `0` | Enable real document verification in demo |
| `LOIP_QWEN_BACKEND` | `ollama` | Qwen backend: `ollama` or `hf` |
| `LOIP_OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `LOIP_QWEN_OLLAMA_MODEL` | `qwen2.5vl:3b` | Ollama model name for Qwen |
| `LOIP_INSIGHTFACE_MODEL` | `buffalo_l` | InsightFace model pack for webcam liveness |
| `UIDAI_PUBLIC_KEY_PATH` | `loip/keys/uidai_public_key.pem` | Path to UIDAI RSA-2048 public key for Aadhaar QR signature verification |
| `QR_NAME_SIMILARITY_THRESHOLD` | `0.80` | Minimum name similarity score (QR vs OCR) |
| `QR_ADDRESS_SIMILARITY_THRESHOLD` | `0.70` | Minimum address similarity score (QR vs OCR) |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Database connection string |
| `PORT` | `5000` | Express backend port |

## Project Structure

```
LOIP/
├── loip/                           # Python backend — 13 domain processors
│   ├── domains/
│   │   ├── document_intel/         #   LayoutLMv3 + PaddleOCR + Surya + Qwen2.5-VL + Donut
│   │   ├── qr_trust/              #   QR Trust Verification — pyzbar/OpenCV, UIDAI RSA, ELA+EXIF
│   │   │   ├── processor.py       #     Orchestrator (detect → parse → verify → cross-check → score)
│   │   │   ├── aadhaar_qr.py      #     UIDAI Secure QR zlib+XML parser + RSA-2048 sig verifier
│   │   │   ├── pan_qr.py          #     PAN QR Base64/pipe-delimited parser
│   │   │   ├── tampering.py       #     ELA (PIL re-save diff) + EXIF metadata tampering detector
│   │   │   └── schemas.py         #     QRTrustResult, AadhaarQRData, PANQRData, QRTrustFlag
│   │   ├── identity_trust/        #   PAN/Aadhaar verification, face match, liveness + QR integration
│   │   ├── income_intel/          #   Multi-source income reconciliation
│   │   ├── affordability/         #   EMI, FOIR, disposable income analysis
│   │   ├── fraud/                 #   Neo4j graph fraud + GraphSAGE anomaly
│   │   ├── risk_decisioning/      #   Rule gates + XGBoost ensemble scoring
│   │   ├── explainability/        #   SHAP + LIME + Qwen3 copilot narrative
│   │   ├── human_review/          #   Review queue, case assignment, overrides
│   │   ├── compliance/            #   DPDP consent, PII masking, KFS, AML
│   │   ├── truth_reconciliation/  #   Cross-source field reconciliation
│   │   ├── mlops/                 #   Model registry, drift monitoring
│   │   └── evidence/              #   Evidence chain schemas
│   ├── keys/
│   │   └── uidai_public_key.pem   #   UIDAI RSA-2048 public key placeholder
│   ├── models/                    # 11 ML model wrappers (mock + real backends)
│   ├── integrations/              # External API clients (CIBIL, NSDL, UIDAI, DigiLocker)
│   ├── pipelines/
│   │   └── onboarding.py          # Main orchestration pipeline
│   ├── schemas/                   # Pydantic models
│   ├── web/
│   │   ├── api.py                 # FastAPI app with 10 route modules
│   │   ├── routes/                # demo, onboard, review, admin, audit, consent, vcip, etc.
│   │   └── templates/             # Jinja2 HTML templates (landing, apply, status, queue, dashboard)
│   ├── scripts/                   # Training, generators, annotation, dataset tools
│   ├── tests/                     # 21 test files, 111 test functions
│   ├── config.py                  # Centralized settings (pydantic-settings)
│   ├── persistence.py             # PostgreSQL async persistence
│   ├── events.py                  # Kafka domain event pipeline
│   ├── graph.py                   # Neo4j identity graph + fraud ring detection
│   ├── storage.py                 # MinIO document storage
│   ├── validation.py              # Aadhaar Verhoeff + MRZ + QR payload parsing
│   ├── docker-compose.yml         # 12 infrastructure services
│   └── pyproject.toml             # Python project config
│
├── frontend/                      # React + Vite SPA (:3000)
│   └── src/
│       ├── App.tsx                # Main app — dark theme, auth routing
│       └── components/
│           ├── AuthPortal.tsx     # JWT login / register
│           ├── CustomerPortal.tsx # Apply, upload docs, track status (SSE)
│           ├── AdminPortal.tsx    # Review queue, approve/reject, bureau drill-down
│           ├── AnalyticsPortal.tsx# Loan analytics, processing metrics, reports
│           └── DevSandbox.tsx     # Test individual engines in isolation
│
├── backend/                       # Express.js API (:5000)
│   └── src/
│       ├── server.ts             # Express app, auth + loan routes
│       ├── db.ts                 # SQLite database (auto-creates tables)
│       ├── queue.ts              # Background job queue for async processing
│       ├── controllers/
│       │   ├── authController.ts # JWT auth (register, login, profile)
│       │   └── loanController.ts # Loan CRUD, doc upload, admin actions
│       ├── engines/
│       │   ├── index.ts          # Engine orchestrator — runs all 14 engines
│       │   ├── ocrEngine.ts      # OCR via Python bridge (PyMuPDF + Tesseract)
│       │   ├── classifier.ts     # Document type classification
│       │   ├── identity.ts       # Identity cross-verification
│       │   ├── face.ts           # Face match scoring
│       │   ├── fraud.ts          # Fraud pattern detection
│       │   ├── bureau.ts         # Credit bureau simulation
│       │   ├── bank.ts           # Bank statement analysis
│       │   ├── income.ts         # Income assessment
│       │   ├── affordability.ts  # Affordability calculation
│       │   ├── risk.ts           # Risk scoring
│       │   ├── decision.ts       # Final decision engine
│       │   ├── docQA.ts          # Document Q&A
│       │   └── documentFraudExpert.ts # Document fraud analysis
│       ├── analytics/            # Analytics controller + router
│       ├── middleware/
│       │   └── auth.ts           # JWT middleware
│       └── utils/
│           ├── geminiVision.ts   # Gemini Vision API integration
│           ├── metadataValidator.ts # Document metadata validation
│           └── crypto.ts         # Encryption utilities
│
├── start-demo.sh                  # One-command full demo launcher
├── LOIP_Presentation.html         # Self-contained slide deck (open in browser)
├── LOIP_BUILD_PLAN.md             # Detailed build plan document
└── .github/workflows/ci.yml      # CI: lint, type-check, test, security audit
```

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

## API Documentation

With the server running, visit **http://localhost:8000/docs** for the full OpenAPI spec.

### FastAPI Endpoints (Python Backend — :8000)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Landing page |
| `/apply` | GET | Demo loan application UI |
| `/apply/submit` | POST | Submit demo application (rate-limited 10/min) |
| `/apply/liveness` | POST | Webcam frame analysis — returns yaw + EAR for liveness challenge |
| `/apply/status/{id}` | GET | Application status page |
| `/apply/mode` | GET | Current mode (mock vs real models) |
| `/onboard` | POST | Full onboarding pipeline (API) |
| `/review/queue` | GET | Human review queue |
| `/review/{case_id}/override` | POST | Submit reviewer override |
| `/evidence/{app_id}/chains` | GET | Evidence traceability chains |
| `/vcip/initiate` | POST | Start V-CIP video KYC session |
| `/compliance/consent` | POST | Record DPDP consent |
| `/ui` | GET | Admin dashboard |
| `/docs` | GET | OpenAPI/Swagger docs |

### Express Endpoints (Node.js Backend — :5000)

| Endpoint | Method | Description |
|----------|--------|-------------|
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
|---------|------|---------|
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
|-------|------|---------|-------------|
| Qwen2.5-VL 3B | Primary document field extraction | `qwen2_5_vl_wrapper.py` | Ollama (verified) |
| LayoutLMv3 | Document type classification | `layoutlmv3_wrapper.py` | HuggingFace transformers |
| PaddleOCR | Primary OCR engine | `paddleocr_wrapper.py` | PaddlePaddle |
| Surya | Secondary OCR (fallback) | `surya_wrapper.py` | surya-ocr |
| Donut | Secondary structured extraction | `donut_wrapper.py` | HuggingFace transformers |
| BGE-M3 | Name/entity similarity | `bge_m3_wrapper.py` | sentence-transformers |
| ArcFace (InsightFace `buffalo_l`) | Face verification + webcam liveness (yaw + blink) | `arcface_wrapper.py` | insightface |
| MiniFASNet | Liveness / anti-spoof (pipeline) | `minifasnet_wrapper.py` | custom |
| XGBoost | Risk scoring + income confidence | `xgboost_wrapper.py` | xgboost |
| LightGBM | Affordability scoring | `lightgbm_wrapper.py` | lightgbm |
| GraphSAGE | Graph fraud anomaly detection | `graphsage_wrapper.py` | PyTorch Geometric |

## QR Trust Verification

LOIP includes a dedicated QR Trust Verification Module that runs on every uploaded Aadhaar and PAN card after OCR extraction. It adds a cryptographic and visual integrity layer on top of standard field matching.

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
|--------|------|----------------|
| QR not found | `QR_NOT_FOUND` | −0.20 |
| QR decode failed | `QR_DECODE_FAILED` | −0.20 |
| Aadhaar RSA signature invalid | `QR_SIGNATURE_INVALID` | −0.35 |
| Aadhaar RSA signature absent | `QR_SIGNATURE_MISSING` | −0.10 |
| Any field mismatch (name/DOB/number) | `QR_*_MISMATCH` | −0.10 each |
| ELA anomaly alone | `QR_ELA_ANOMALY` | −0.10 |
| EXIF anomaly alone | `QR_EXIF_ANOMALY` | −0.10 |
| Both ELA + EXIF anomaly | `QR_TAMPERED` | −0.30 |

The final `trust_score` is weighted at 25% of the identity confidence delta, feeding into the XGBoost ensemble risk score.

### Aadhaar Secure QR Signature Verification

UIDAI embeds an RSA-2048 PKCS#1 v1.5 + SHA-256 signature in every Secure QR. To enable real verification:

1. Obtain the official public key from [developer.uidai.gov.in](https://developer.uidai.gov.in)
2. Place it at `loip/keys/uidai_public_key.pem` (or set `UIDAI_PUBLIC_KEY_PATH` env var)

Without the real key, signature verification is disabled with a warning — the pipeline continues with `signature_valid=False` and a `QR_SIGNATURE_MISSING` flag.

### DPDP Act Compliance

- Aadhaar UID is **masked to the last 4 digits** at parse time and never stored or serialized in full
- XML parsing uses `defusedxml` to prevent entity expansion DoS attacks
- The `loip/keys/` directory is in `.gitignore` (except the placeholder stub)

## Regulatory Compliance

- **RBI Digital Lending Guidelines**: Key Fact Statement (KFS) generation, cooling-off period, NACH mandate
- **DPDP Act 2023**: Consent management, data deletion, PII masking (Presidio + regex fallback)
- **PMLA / AML**: PEP screening, AML risk assessment, SAR flagging
- **RBI V-CIP**: Video KYC lifecycle with geotag, OVD presentation, random questions, recording storage
- **Data Residency**: India-region enforcement check for all service endpoints

## License

Private repository — all rights reserved.
