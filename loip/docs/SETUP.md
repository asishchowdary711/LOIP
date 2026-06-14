# SETUP

Development environment setup for LOIP (Loan Onboarding Intelligence Platform).

## Prerequisites

- Python 3.11+ (the main app venv on this machine runs Python 3.14; a separate
  Python 3.11 venv is used for OCR tooling — see below)
- `poppler` (provides `pdftoppm`, used by `pdf2image` for PDF-based document
  generators: salary_slip, bank_statement, form16, itr)

## Three virtual environments

This project uses **three separate venvs**:

| Venv | Python | Purpose |
|---|---|---|
| `.venv` | 3.14 | Main application: FastAPI web layer, pipelines, domains, schemas, tests |
| `.venv-ocr` | 3.11 | OCR annotation tooling (`paddleocr`/`paddlepaddle`, which require Python <=3.12) |
| `.venv-ml` | 3.11 | Phase 1 tabular/graph ML wrappers (XGBoost/LightGBM/GraphSAGE) and training scripts; also hosts LayoutLMv3/Donut/Qwen2.5-VL once Phase B is activated (see `docs/RUNBOOK.md`) |

Create the main venv and install dependencies:

```bash
cd loip
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

The OCR venv (only needed for re-running the annotation pipeline in
`scripts/annotate/`) was created via:

```bash
~/.local/bin/python3.11 -m venv .venv-ocr
.venv-ocr/bin/pip install paddleocr paddlepaddle pdf2image pillow click
```

The ML venv (needed to retrain or test the XGBoost/LightGBM/GraphSAGE
wrappers in `loip/models/`) was created via:

```bash
~/.local/bin/python3.11 -m venv .venv-ml
.venv-ml/bin/pip install -e ".[tabular-ml]"
```

**macOS arm64 troubleshooting**: `xgboost` and `lightgbm` both depend on the
OpenMP runtime, which Apple's toolchain doesn't ship. If import fails with
`Library not loaded: @rpath/libomp.dylib`, install it with:

```bash
brew install libomp
```

The checkpoints these wrappers load (`models/checkpoints/xgboost_*.json`,
`lightgbm_affordability.txt`, `graphsage_fraud.joblib`) are committed to the
repo, so `.venv-ml` is only needed to retrain them
(`scripts/training/train_*.py`) or run their tests
(`.venv-ml/bin/python -m pytest tests/models/ -q`).

## Database (SQLite dev path)

Production targets PostgreSQL (see `docker-compose.yml`), but for local
development without Docker, Alembic migrations also run against SQLite:

```bash
cd loip
DATABASE_URL=sqlite+aiosqlite:///data/dev.db .venv/bin/alembic upgrade head
```

Migration `001_initial_schema` has been verified to apply cleanly (`upgrade
head` / `downgrade base`) against this SQLite path.

## Running tests

```bash
cd loip
PYTHONPATH=. .venv/bin/python -m pytest -q
```

(Use `PYTHONPATH=.` / run from the `loip/` directory — there is no `loip`
package installed on `PYTHONPATH` by default in this environment. `pytest`
config (`testpaths`, `asyncio_mode=auto`) lives in `pyproject.toml`.)

## Linting and type checking

```bash
cd loip
.venv/bin/ruff check .
.venv/bin/mypy .
```

## Docker Compose (infrastructure services)

`docker-compose.yml` (in `loip/`) defines the full service set: PostgreSQL,
MinIO, OpenSearch, Neo4j, Kafka/Zookeeper, Redis, MLflow, Prometheus,
Grafana, and Ollama.

The **core data-plane services** (PostgreSQL, MinIO + bucket init, Redis) are
the ones wired into the running app today. Bring them up with:

```bash
cd loip
docker compose up -d postgres minio minio-init redis
docker compose ps          # all should be "healthy"
```

`minio-init` creates one bucket per document type plus `evidence`, `models`,
and `annotations`. The MinIO console is at http://localhost:9001
(minioadmin / minioadmin); the S3 API is on :9000.

When MinIO is up, `POST /onboard` and the demo seeder persist each uploaded
document to its bucket and stamp the object id onto every document-derived
evidence field (`SourceLocation.document_id`), making figures traceable to a
stored object. If MinIO is **not** running, both paths degrade gracefully —
the pipeline still runs, evidence chains just omit document ids.

The heavier services (OpenSearch, Neo4j, Kafka, MLflow, Prometheus, Grafana,
Ollama) are defined and start with `docker compose up -d`, but are not yet
wired into the request path. `.env.example` documents all variables; copy it
to `.env` to override the compose defaults.

## Environment variables

See `.env.example` for the full list. Notably:

- `DATA_REGION=ap-south-1`, `ENFORCE_DATA_RESIDENCY=true` — RBI data
  localization (see `COMPLIANCE.md`)
- `RATE_LIMIT_DEFAULT=100/minute`, `RATE_LIMIT_UPLOAD=10/minute` — applied via
  `slowapi` (see `API.md`)
- KYC/bureau API keys (`NSDL_API_KEY`, `UIDAI_API_KEY`, `CIBIL_API_KEY`,
  `EXPERIAN_API_KEY`, `DIGILOCKER_API_KEY`) — if empty, mock-mode stubs are
  used throughout the pipeline (`mock_mode=True` is the default for every
  processor and model wrapper).
