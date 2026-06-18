# LOIP — Loan Onboarding Intelligence Platform

**An end-to-end AI-powered personal loan onboarding system for the Indian market.**

LOIP ingests identity documents (PAN, Aadhaar, salary slips, bank statements, ITR, GST returns), verifies applicant identity against government databases (NSDL, UIDAI), reconciles income from multiple sources, assesses affordability, detects fraud through graph analysis, and produces an explainable approve/review/reject decision — all within a single async pipeline backed by 11 ML model wrappers and 13 domain processors.

Built for RBI Digital Lending Guidelines, DPDP Act 2023 compliance, and PMLA/AML screening.

---

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Web Layer                            │
│  /apply (Demo UI)  /onboard (API)  /ui (Admin)  /vcip (V-KYC)  │
└───────────┬─────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   OnboardingPipeline                             │
│  9 domain processors executed sequentially with evidence chains  │
└───┬───────┬────────┬──────────┬────────┬────────┬──────────┬────┘
    │       │        │          │        │        │          │
    ▼       ▼        ▼          ▼        ▼        ▼          ▼
 Doc      QR       Identity  Income   Afford-  Fraud   Explain-
 Intel    Trust    Trust     Intel    ability  Intel   ability
    │       │        │          │        │        │          │
    ▼       ▼        ▼          ▼        ▼        ▼          ▼
 5 ML   pyzbar/  BGE-M3   XGBoost  LightGBM Graph-   SHAP/
 models  OpenCV  ArcFace                    SAGE     LIME
         UIDAI   MiniFAS                    Neo4j    Copilot
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

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for infrastructure services)
- A webcam (for the in-browser liveness challenge on the demo UI)
- [Ollama](https://ollama.ai/) (optional, for real document extraction)

### 1. Start Infrastructure

```bash
cd loip
docker compose up -d
```

This starts: PostgreSQL 16, MinIO, Kafka + Zookeeper, Neo4j 5, OpenSearch, Redis 7, MLflow, Prometheus, Grafana, and Ollama.

### 2. Install Python Dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

> **QR Trust dependencies** — pyzbar requires the `libzbar` system library:
> ```bash
> # macOS
> brew install zbar
> # Debian / Ubuntu
> sudo apt-get install libzbar0
> # Docker — add before pip install in your RUN layer
> ```

### 3. Run Database Migrations

```bash
cd loip
alembic upgrade head
```

### 4. Start the Server

```bash
# Mock mode (default — no ML weights needed, fast, CI-safe)
uvicorn loip.web.api:app --reload --host 0.0.0.0 --port 8000

# With real document extraction (requires Ollama + qwen2.5vl:3b)
LOIP_DEMO_REAL_MODELS=1 uvicorn loip.web.api:app --reload --host 0.0.0.0 --port 8000
```

### 5. Access the Demo UI

Open **http://localhost:8000/apply** in your browser.

**Demo UI Features:**
- 7-field loan application form (name, mobile, PAN, Aadhaar, employment type, monthly income, loan amount)
- 4 document upload slots (Aadhaar, PAN, salary slip, bank statement) — accepts **images and PDFs**
- Animated 4-stage per-document processing (Uploading → OCR → Extracting → Validating)
- **Webcam liveness challenge** powered by InsightFace (`buffalo_l` model): turn right → turn left → blink — submit is disabled until all 3 steps pass
- Real-time approve/review/reject decision banner
- Application data stored as JSON in `loip/data/demo_applications/` (no database required for demo)

**Other UI endpoints:**
- **http://localhost:8000/ui** — Admin dashboard with review queue statistics
- **http://localhost:8000/ui/queue** — Human review queue
- **http://localhost:8000/docs** — OpenAPI/Swagger interactive documentation

> **Interactive Presentation:** Open `LOIP_Presentation.html` in any browser for a self-contained slide deck covering the full platform architecture, pipeline stages, and demo walkthrough — no server required.

### 6. Enable Real Document Verification (Optional)

```bash
# Install and start Ollama
brew install ollama  # macOS
ollama serve &

# Pull the Qwen2.5-VL model (3.2 GB)
ollama pull qwen2.5vl:3b

# Start with real models
LOIP_DEMO_REAL_MODELS=1 uvicorn loip.web.api:app --reload --port 8000
```

When `LOIP_DEMO_REAL_MODELS=1` is set, document extraction uses the real Qwen2.5-VL model via Ollama while keeping external API clients (CIBIL, NSDL, UIDAI) in mock mode.

**Environment variables for model configuration:**

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

## Project Structure

```
loip/
├── domains/                    # 13 domain processors
│   ├── document_intel/         #   LayoutLMv3 + PaddleOCR + Surya + Qwen2.5-VL + Donut
│   ├── qr_trust/               #   QR Trust Verification — pyzbar/OpenCV decode, UIDAI RSA sig, ELA+EXIF tamper
│   │   ├── processor.py        #     Orchestrator (detect → parse → verify → cross-check → score)
│   │   ├── aadhaar_qr.py       #     UIDAI Secure QR zlib+XML parser + RSA-2048 signature verifier
│   │   ├── pan_qr.py           #     Income Tax Dept PAN QR Base64/pipe-delimited parser
│   │   ├── tampering.py        #     ELA (PIL re-save diff) + EXIF metadata tampering detector
│   │   └── schemas.py          #     QRTrustResult, AadhaarQRData, PANQRData, QRTrustFlag …
│   ├── identity_trust/         #   PAN/Aadhaar verification, face match, liveness + QR trust integration
│   ├── income_intel/           #   Multi-source income reconciliation
│   ├── affordability/          #   EMI, FOIR, disposable income analysis
│   ├── fraud/                  #   Neo4j graph fraud + GraphSAGE anomaly
│   ├── risk_decisioning/       #   Rule gates + XGBoost ensemble scoring
│   ├── explainability/         #   SHAP + LIME + Qwen3 copilot narrative
│   ├── human_review/           #   Review queue, case assignment, overrides
│   ├── compliance/             #   DPDP consent, PII masking, KFS, AML
│   ├── truth_reconciliation/   #   Cross-source field reconciliation
│   ├── mlops/                  #   Model registry, drift monitoring
│   └── evidence/               #   Evidence chain schemas
├── keys/
│   └── uidai_public_key.pem    #   UIDAI RSA-2048 public key placeholder (replace with real key)
├── models/                     # 11 ML model wrappers (mock + real backends)
│   ├── qwen2_5_vl_wrapper.py   #   Ollama/HF/mock backends for doc extraction
│   ├── layoutlmv3_wrapper.py   #   Document classification
│   ├── paddleocr_wrapper.py    #   Primary OCR
│   ├── surya_wrapper.py        #   Secondary OCR (fallback)
│   ├── donut_wrapper.py        #   Secondary structured extraction
│   ├── bge_m3_wrapper.py       #   Name/entity similarity embeddings
│   ├── arcface_wrapper.py      #   Face verification
│   ├── minifasnet_wrapper.py   #   Liveness / anti-spoofing
│   ├── xgboost_wrapper.py      #   Risk + income confidence scoring
│   ├── lightgbm_wrapper.py     #   Affordability scoring
│   └── graphsage_wrapper.py    #   Graph fraud anomaly detection
├── integrations/               # External API clients
│   ├── cibil_client.py         #   Credit bureau
│   ├── nsdl_client.py          #   PAN verification
│   ├── uidai_client.py         #   Aadhaar OTP verification
│   ├── digilocker_client.py    #   DigiLocker document fetch
│   ├── experian_client.py      #   Alternate bureau
│   └── mca21_client.py         #   Company verification
├── pipelines/
│   └── onboarding.py           # Main orchestration pipeline
├── schemas/                    # Pydantic models (667 LOC)
├── web/
│   ├── api.py                  # FastAPI app with 9 route modules
│   ├── routes/                 # 10 API route files (1,095 LOC)
│   └── templates/              # 5 Jinja2 HTML templates
├── scripts/
│   ├── training/               # 8 fine-tuning + training scripts
│   ├── generators/             # 9 synthetic document generators
│   ├── annotate/               # Annotation pipeline
│   └── download_datasets.py    # Dataset download with budget control
├── tests/                      # 21 test files, 111 test functions
├── config.py                   # Centralized settings (pydantic-settings)
├── persistence.py              # PostgreSQL async persistence
├── events.py                   # Kafka domain event pipeline
├── graph.py                    # Neo4j identity graph + fraud ring detection
├── storage.py                  # MinIO document storage
├── validation.py               # Aadhaar Verhoeff + passport MRZ + QR payload parsing
├── evaluate.py                 # CLI pipeline evaluation tool
├── docker-compose.yml          # 12 infrastructure services
└── alembic/                    # Database migrations (2 versions)
```

## Running Tests

```bash
cd loip
DATABASE_URL=sqlite+aiosqlite:///data/dev.db pytest -q
```

## API Documentation

With the server running, visit **http://localhost:8000/docs** for the full OpenAPI spec.

Key API endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/apply` | GET | Demo loan application UI |
| `/apply/submit` | POST | Submit demo application (rate-limited 10/min) |
| `/liveness` | POST | Webcam frame analysis — returns head yaw + eye-aspect-ratio for liveness challenge |
| `/onboard` | POST | Full onboarding pipeline (API) |
| `/review/queue` | GET | Human review queue |
| `/review/{case_id}/override` | POST | Submit reviewer override |
| `/evidence/{app_id}/chains` | GET | Evidence traceability chains |
| `/vcip/initiate` | POST | Start V-CIP video KYC session |
| `/compliance/consent` | POST | Record DPDP consent |
| `/ui` | GET | Admin dashboard |
| `/health/ready` | GET | Readiness check (all deps) |

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
| ArcFace (InsightFace `buffalo_l`) | Face verification + webcam liveness challenge (yaw + blink) | `arcface_wrapper.py` | insightface |
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
