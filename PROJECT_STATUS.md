# LOIP Project Status

> Last updated: 2026-06-15

## Overall Completion: 62%

This assessment is based on repository evidence only — actual code, tests, configurations, and git history.

---

## Module-by-Module Status

### 1. Loan Application UI — 90%

| Component | Status | Evidence |
|-----------|--------|----------|
| Customer demo form (`/apply`) | **Done** | `loip/web/routes/demo.py` (201 LOC), `loip/web/templates/apply.html` (15.9 KB) |
| 7 form fields | **Done** | name, mobile, PAN, Aadhaar, employment, income, loan amount |
| 4 document uploads | **Done** | Aadhaar, PAN, salary slip, bank statement; image-only (`accept="image/*"`) |
| Animated processing states | **Done** | Client-side 4-stage animation per document |
| Decision banner | **Done** | Approve/review/reject reconciled from pipeline response |
| Local JSON storage | **Done** | `loip/data/demo_applications/` (gitignored) |
| Admin dashboard (`/ui`) | **Done** | Dashboard, queue, review detail pages (5 Jinja2 templates) |
| PDF upload support | **Gap** | UI only accepts images; backend uses `cv2.imdecode` |
| Production-grade forms | **Gap** | No client-side validation beyond required fields; no accessibility audit |

### 2. Document Upload & Storage — 85%

| Component | Status | Evidence |
|-----------|--------|----------|
| Image upload via form | **Done** | `cv2.imdecode` in `demo.py` |
| MinIO document storage | **Done** | `loip/storage.py` — 11 buckets, per-type storage |
| Document ID traceability | **Done** | `bucket/uuid.ext` format, linked to evidence chains |
| Docker MinIO + init | **Done** | `docker-compose.yml` lines 14-55 |
| PDF-to-image conversion | **Gap** | PDFs must be manually converted before upload |
| Multi-page document support | **Gap** | Only single images processed |

### 3. OCR Pipeline — 75%

| Component | Status | Evidence |
|-----------|--------|----------|
| Document classification (LayoutLMv3) | **Done** | `loip/models/layoutlmv3_wrapper.py` (110 LOC), mock + real |
| Primary OCR (PaddleOCR) | **Done** | `loip/models/paddleocr_wrapper.py` (48 LOC), mock + real |
| Secondary OCR (Surya) | **Done** | `loip/models/surya_wrapper.py` (16 LOC), mock + real |
| OCR confidence fallback | **Done** | `DocumentIntelligenceProcessor.perform_ocr()` — dual-OCR with threshold |
| Primary extraction (Qwen2.5-VL) | **Done** | `loip/models/qwen2_5_vl_wrapper.py` (212 LOC), Ollama backend verified |
| Secondary extraction (Donut) | **Done** | `loip/models/donut_wrapper.py` (85 LOC), mock + HF |
| Extraction fallback logic | **Done** | Confidence threshold comparison in `extract_fields()` |
| Real Ollama extraction | **Done** | Verified: PAN fields matched ground truth (commit 2959576) |
| LayoutLMv3 fine-tuned checkpoint | **Partial** | Smoke-test checkpoint exists; not production-grade |
| Fine-tuning scripts | **Done** | 3 scripts: `finetune_layoutlmv3.py`, `finetune_donut.py`, `finetune_qwen25vl.py` |
| Trained model weights | **Gap** | No production-trained weights; all models use mock or base pretrained |
| Indian document training data | **Gap** | Only 25-sample synthetic annotation corpus |

### 4. Identity Verification — 80%

| Component | Status | Evidence |
|-----------|--------|----------|
| PAN format validation | **Done** | Regex in identity processor |
| PAN NSDL verification | **Done** | `loip/integrations/nsdl_client.py` (95 LOC), mock + real client |
| Aadhaar Verhoeff checksum | **Done** | `loip/validation.py` — real Verhoeff implementation |
| Aadhaar UIDAI OTP verification | **Done** | `loip/integrations/uidai_client.py` (116 LOC), mock + real client |
| Face match (ArcFace) | **Done** | `loip/models/arcface_wrapper.py` (11 LOC), mock + real |
| Liveness detection (MiniFASNet) | **Done** | `loip/models/minifasnet_wrapper.py` (11 LOC), mock + real |
| Name cross-check (BGE-M3) | **Done** | `loip/models/bge_m3_wrapper.py` (22 LOC), cosine similarity |
| DOB cross-check | **Done** | Exact match between document and application |
| Document metadata tamper check | **Done** | Photoshop detection in PDF metadata |
| Confidence scoring heuristic | **Done** | Penalty-based from 1.0 per failed check |
| Real API endpoints configured | **Gap** | NSDL/UIDAI clients have no production endpoints; mock only |
| Passport MRZ validation | **Done** | ICAO 9303 TD3 in `loip/validation.py` |

### 5. Evidence Graph & Traceability — 80%

| Component | Status | Evidence |
|-----------|--------|----------|
| Evidence chain schema | **Done** | `loip/schemas/evidence.py` (80 LOC) — claim, supporting, contradicting, method |
| Source location tracking | **Done** | `SourceLocation` with document_id, extraction_method, model_version |
| Document-backed evidence | **Done** | Income processor builds `ExtractedField` linked to MinIO objects |
| Evidence API endpoint | **Done** | `GET /evidence/{app_id}/chains`, `GET /evidence/{app_id}/source/{field}` |
| Evidence persistence | **Done** | `EvidenceRecord` table in PostgreSQL |
| Evidence visualization in UI | **Done** | Review detail page shows evidence chains |
| Contradicting evidence tracking | **Partial** | Schema supports it; processors don't populate contradicting fields |

### 6. Truth Reconciliation Engine — 40%

| Component | Status | Evidence |
|-----------|--------|----------|
| Domain directory exists | **Done** | `loip/domains/truth_reconciliation/` |
| Source-trust weighted averaging | **Done** | Implemented in `IncomeIntelligenceProcessor` (5 sources, configurable weights) |
| Reconciliation methods defined | **Done** | Enum: `SOURCE_TRUST_WEIGHTED`, `HIGHEST_CONFIDENCE`, `COMPUTED` |
| Cross-source anomaly detection | **Done** | Salary slip vs bank mismatch, income inflation detection |
| Dedicated reconciliation processor | **Gap** | `truth_reconciliation/__init__.py` is empty; logic is inline in income/identity processors |
| Multi-field reconciliation | **Gap** | Only income and name fields are reconciled across sources |
| Reconciliation audit trail | **Partial** | Evidence chains capture method but not full reconciliation history |

### 7. Affordability Assessment — 75%

| Component | Status | Evidence |
|-----------|--------|----------|
| EMI calculation | **Done** | Standard reducing-balance formula in `AffordabilityProcessor` |
| FOIR computation | **Done** | `total_obligations / verified_monthly_income` |
| Disposable income | **Done** | Income − obligations − estimated expenses |
| LightGBM scoring | **Done** | `loip/models/lightgbm_wrapper.py` (48 LOC), mock + real |
| Anomaly flags | **Done** | FOIR_EXCEEDED, FOIR_MARGINAL, DISPOSABLE_INCOME_INSUFFICIENT |
| Evidence chain for FOIR | **Done** | Computed evidence chain attached |
| Existing obligations parsing | **Gap** | Hardcoded to 0.0; bank statement obligation parsing not implemented |
| Expense estimation | **Gap** | Fixed ₹15,000/month; no dynamic computation |
| Training script | **Done** | `train_affordability_lightgbm.py` (58 LOC) |

### 8. Fraud Detection — 80%

| Component | Status | Evidence |
|-----------|--------|----------|
| Liveness/spoof fraud signal | **Done** | Checks `liveness_verified` from identity result |
| Passport MRZ forgery check | **Done** | ICAO 9303 validation in fraud processor |
| Neo4j identity graph | **Done** | `loip/graph.py` (141 LOC), 8 node types, uniqueness constraints |
| PAN farming detection | **Done** | Cypher: shared phone/email → multiple distinct PANs |
| Synthetic identity ring | **Done** | Cypher: shared device → multiple persons |
| Address inconsistency ring | **Done** | Cypher: shared address → ≥3 applications |
| GraphSAGE anomaly scoring | **Done** | `loip/models/graphsage_wrapper.py` (97 LOC), mock + real |
| Fraud score aggregation | **Done** | `max(severity)` across all signals |
| Hard reject threshold | **Done** | `fraud_score > 0.80` → immediate reject |
| Behavioral analytics | **Gap** | No session/device behavioral analysis |
| Training script | **Done** | `train_fraud_graphsage.py` (52 LOC) |

### 9. Risk Scoring — 85%

| Component | Status | Evidence |
|-----------|--------|----------|
| Hard reject rules | **Done** | 10 hard-reject conditions (identity, credit, income, affordability, fraud, V-CIP) |
| Review trigger rules | **Done** | 8 review flag conditions |
| XGBoost ensemble scoring | **Done** | `loip/models/xgboost_wrapper.py` (63 LOC), 7 input features |
| Three-tier decision | **Done** | APPROVE (≥0.70), REVIEW (0.40–0.70), REJECT (<0.40) |
| V-CIP regulatory gate | **Done** | Disbursal blocked if V-CIP required but not completed |
| Evidence chain aggregation | **Done** | Chains from all sub-results collected |
| Training script | **Done** | `train_risk_xgboost.py` (58 LOC) |
| Trained production model | **Gap** | No trained weights; uses mock scorer |

### 10. Audit Trail — 70%

| Component | Status | Evidence |
|-----------|--------|----------|
| Audit log table | **Done** | `AuditLogRecord` in `loip/schemas/db_models.py` |
| Decision audit entries | **Done** | Written on every `save_decision()` call |
| Override audit entries | **Done** | Written on every `save_override()` call |
| Explainability storage | **Done** | SHAP/LIME/copilot results stored per application |
| Audit API route | **Done** | `loip/web/routes/audit.py` (28 LOC) |
| Consent audit | **Done** | DPDP consent records in DB with timestamps |
| Data deletion tombstones | **Done** | `audit_tombstone_id` in deletion records |
| Audit log search/filtering | **Gap** | No search endpoint or filtering |
| Audit log export | **Gap** | No CSV/PDF export capability |

### 11. Human Review Queue — 90%

| Component | Status | Evidence |
|-----------|--------|----------|
| Case creation from decisions | **Done** | Auto-created for review/reject decisions |
| Queue listing + filtering | **Done** | Status, assigned_to, risk score, sort, pagination |
| Queue summary statistics | **Done** | Pending, in-progress, completed, escalated, avg age |
| Case detail view | **Done** | Full decision data, evidence chains, explainability |
| Case assignment | **Done** | Assign to specific reviewer |
| Override workflow | **Done** | Approve/reject/escalate with reason codes |
| Override persistence | **Done** | PostgreSQL via `ReviewOverrideRecord` |
| Retraining data export | **Done** | `get_retraining_data()` returns override feedback |
| Admin dashboard UI | **Done** | `dashboard.html`, `queue.html`, `review_detail.html` |
| Form-based override UI | **Done** | POST `/ui/review/{case_id}/override` |
| Queue rehydration from DB | **Done** | `web/startup.py` loads decisions on startup |
| SLA tracking | **Partial** | Age in queue tracked; no SLA thresholds or alerts |

### 12. API Layer — 85%

| Component | Status | Evidence |
|-----------|--------|----------|
| FastAPI application | **Done** | `loip/web/api.py` with 9 route modules |
| Rate limiting | **Done** | slowapi on demo submit (10/min) |
| CORS middleware | **Done** | All origins allowed (dev config) |
| Health endpoints | **Done** | `/health`, `/health/ready` (checks PG, MinIO, Kafka, Neo4j), `/health/live` |
| OpenAPI documentation | **Done** | Auto-generated at `/docs` |
| Auth middleware | **Done** | `loip/web/auth.py` — permission-based access control |
| RBAC permissions | **Done** | `onboard:read`, `onboard:write`, `audit:read` etc. |
| 10 route files | **Done** | onboard, review, audit, evidence, admin, ui, consent, vcip, demo |
| Request validation | **Done** | Pydantic models on all endpoints |
| Error handling | **Partial** | Broad `Exception` catches; no structured error responses |
| API versioning | **Gap** | No `/v1/` prefix or versioning strategy |

### 13. Database Layer — 70%

| Component | Status | Evidence |
|-----------|--------|----------|
| SQLAlchemy async ORM | **Done** | `loip/persistence.py` (211 LOC), async sessionmaker |
| DB models | **Done** | `loip/schemas/db_models.py` (125 LOC) — 5 tables |
| Alembic migrations | **Done** | 2 migration versions (`001_initial_schema`, `002_application_decision_json`) |
| Decision persistence | **Done** | `save_decision()`, `load_decisions()` |
| Override persistence | **Done** | `save_override()` |
| Evidence persistence | **Done** | `EvidenceRecord` table |
| Consent persistence | **Done** | `ConsentRecordDB` table |
| PostgreSQL in Docker | **Done** | PostgreSQL 16 Alpine in `docker-compose.yml` |
| Connection pooling | **Done** | `pool_pre_ping=True` on async engine |
| Seed script | **Done** | `loip/scripts/seed_db.py` |
| Idempotent re-saves | **Done** | Existing records deleted before re-insert |
| Index optimization | **Gap** | No custom indexes beyond PK |
| Connection retry logic | **Gap** | No retry/backoff on connection failure |
| Read replicas | **Gap** | Single-node only |

### 14. Model Fine-Tuning Pipeline — 55%

| Component | Status | Evidence |
|-----------|--------|----------|
| Fine-tune LayoutLMv3 | **Done** | `loip/scripts/training/finetune_layoutlmv3.py` (150 LOC) |
| Fine-tune Donut | **Done** | `loip/scripts/training/finetune_donut.py` (148 LOC) |
| Fine-tune Qwen2.5-VL | **Done** | `loip/scripts/training/finetune_qwen25vl.py` (153 LOC) — LoRA |
| Train risk XGBoost | **Done** | `loip/scripts/training/train_risk_xgboost.py` (58 LOC) |
| Train income XGBoost | **Done** | `loip/scripts/training/train_income_xgboost.py` (58 LOC) |
| Train affordability LightGBM | **Done** | `loip/scripts/training/train_affordability_lightgbm.py` (58 LOC) |
| Train fraud GraphSAGE | **Done** | `loip/scripts/training/train_fraud_graphsage.py` (52 LOC) |
| Synthetic data generation | **Done** | `loip/scripts/training/generate_synthetic_dataset.py` (289 LOC) |
| Synthetic document generators | **Done** | 9 generators (PAN, Aadhaar, salary slip, bank statement, ITR, etc.) |
| Dataset download + budget control | **Done** | `loip/scripts/download_datasets.py` with size caps |
| DocVQA evaluation script | **Done** | `loip/scripts/evaluate_qwen_docvqa.py` |
| Annotation pipeline | **Done** | `loip/scripts/annotate/` (generate, validate, label schema) |
| MLflow integration | **Partial** | Docker service defined; not wired into training scripts |
| Trained production weights | **Gap** | No trained models checked in or deployed |
| Training CI/CD pipeline | **Gap** | No automated training triggers |
| Indian document training corpus | **Gap** | Only 25-sample synthetic annotation set |

### 15. BGE-M3 Embeddings — 50%

| Component | Status | Evidence |
|-----------|--------|----------|
| Wrapper implementation | **Done** | `loip/models/bge_m3_wrapper.py` (22 LOC) |
| Mock mode (string matching) | **Done** | Exact/substring match returns 1.0/0.85/0.5 |
| Real mode (sentence-transformers) | **Done** | `SentenceTransformer('BAAI/bge-m3')` cosine similarity |
| Used in identity trust | **Done** | Name cross-check: PAN name vs Aadhaar name vs application name |
| Ollama local availability | **Partial** | `bge-m3` model pulled locally but not used via Ollama backend |
| Embedding-based RAG search | **Gap** | No vector store or RAG pipeline implemented |
| Document similarity search | **Gap** | Not implemented |

### 16. RAG System — 10%

| Component | Status | Evidence |
|-----------|--------|----------|
| OpenSearch in Docker | **Done** | `docker-compose.yml` line 58-69, but wired=None in healthcheck |
| BGE-M3 embeddings available | **Done** | Wrapper exists with real backend support |
| Vector indexing pipeline | **Gap** | Not implemented |
| Document chunking | **Gap** | Not implemented |
| Retrieval-augmented generation | **Gap** | Not implemented |
| Semantic search API | **Gap** | Not implemented |

### 17. Deployment Infrastructure — 55%

| Component | Status | Evidence |
|-----------|--------|----------|
| Docker Compose (12 services) | **Done** | `loip/docker-compose.yml` (202 LOC) |
| GitHub Actions CI | **Done** | `.github/workflows/ci.yml` — test + security jobs |
| Pytest test suite | **Done** | 21 test files, 111 test functions |
| Security scanning | **Done** | pip-audit, bandit, safety in CI |
| Linting (ruff) | **Partial** | Runs in CI but `continue-on-error` (362 findings) |
| Type checking (mypy) | **Partial** | Runs in CI but `continue-on-error` |
| Health endpoints | **Done** | `/health`, `/health/ready`, `/health/live` |
| Prometheus + Grafana | **Done** | Docker services defined; no custom dashboards |
| Dockerfile for app | **Gap** | No Dockerfile for the FastAPI application itself |
| Kubernetes manifests | **Gap** | Not implemented |
| Environment configuration | **Done** | `loip/config.py` with pydantic-settings, `.env` support |
| Production hardening | **Gap** | Debug CORS (`allow_origins=*`), no TLS, no secrets management |

---

## Gaps: Problem Statement vs Definition of Done vs Current State

### Critical Gaps

| Gap | Problem Statement Need | Current State | Impact |
|-----|----------------------|---------------|--------|
| **No trained ML models** | Real document processing | All ML models run in mock mode by default; Qwen via Ollama is the only verified real backend | Demo shows mock decisions unless Ollama is running |
| **No production API endpoints** | Government database verification | CIBIL/NSDL/UIDAI/DigiLocker clients are mock-only | Identity verification returns canned results |
| **No RAG system** | Intelligent document search | OpenSearch container exists but no indexing or query pipeline | No semantic search capability |
| **No application Dockerfile** | Cloud deployment | Docker Compose has infra but no app container | Can't deploy to k8s/ECS/Cloud Run |
| **Limited training data** | Production-grade models | 25-sample synthetic corpus only | Models can't be fine-tuned for production accuracy |

### Moderate Gaps

| Gap | Impact |
|-----|--------|
| No PDF upload support in demo UI | Users must convert PDFs to images manually |
| Existing obligations not parsed from bank statements | FOIR based on proposed EMI only |
| No audit log search/export | Auditors can't query historical decisions |
| Truth reconciliation not a standalone processor | Logic scattered across income/identity processors |
| Linting debt (362 ruff findings, 95 bandit findings) | CI runs non-blocking; technical debt accumulating |
| No API versioning | Breaking changes can't be introduced safely |

### Low-Priority Gaps

| Gap | Impact |
|-----|--------|
| Redis not wired into request path | No caching layer active |
| OpenSearch not wired into request path | No full-text search |
| No Kubernetes manifests | Docker Compose sufficient for demo |
| Prometheus has no custom metrics | Only default scraping |
| MLflow not wired into training scripts | No experiment tracking in practice |

---

## Test Coverage Summary

| Test Category | Files | Tests | Coverage Area |
|---------------|-------|-------|---------------|
| Pipeline | 14 | ~70 | Onboarding, identity, income, affordability, bureau, fraud, events, persistence, validation, explainability, traceability, VCIP, self-employed |
| Models | 4 | ~20 | XGBoost, LightGBM, GraphSAGE, DocVQA evaluation |
| Compliance | 2 | ~10 | DPDP compliance, data residency |
| Annotation | 1 | ~5 | Annotation pipeline |
| Fixtures | 11 | - | Test case factories (clean salaried, self-employed, mismatches, fraud) |
| **Total** | **21** | **~111** | |

## Codebase Statistics

| Metric | Value |
|--------|-------|
| Total Python files | 132 |
| Total Python LOC | ~14,300 |
| Domain processors | 12 |
| ML model wrappers | 11 |
| External API clients | 6 |
| API route files | 10 |
| HTML templates | 5 |
| Pydantic schemas | 11 files (667 LOC) |
| Database tables | 5 |
| Kafka topics | 8 |
| MinIO buckets | 11 |
| Docker services | 12 |
| Test files | 21 |
| Test functions | ~111 |
| Git commits | 20 |
