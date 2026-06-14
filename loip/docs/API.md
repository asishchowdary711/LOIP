# API

LOIP exposes a FastAPI app at `loip.web.api:app`. Interactive docs are
available at `/docs` (Swagger UI) and `/redoc`.

## Authentication & RBAC

All routes (except `/health*`) accept an `X-API-Key` header. If no key is
provided, requests are treated as `anonymous`/`admin` for local development
(`web/auth.py::get_current_user`) — **do not rely on this in production**.

Dev API keys (`web/auth.py::_API_KEYS`):

| Key | Role |
|---|---|
| `dev-key-001` | `admin` |
| `reviewer-key-001` | `reviewer` |
| `senior-key-001` | `senior_reviewer` |
| `consumer-key-001` | `api_consumer` |
| `compliance-key-001` | `compliance_officer` |

### Roles & permissions

| Role | Permissions |
|---|---|
| `admin` | `*` (all), plus explicit `admin:read`/`admin:write` |
| `manager` | onboard, review, audit, compliance:read, mlops:read |
| `senior_reviewer` | onboard:read, review:*, audit:read |
| `reviewer` | onboard:read, review:*, audit:read |
| `api_consumer` | onboard:read/write, audit:read |
| `compliance_officer` | compliance:*, audit:read, review:read |

## Rate limiting

Implemented via `slowapi` (`web/auth.py::limiter`), keyed by `X-API-Key`
(falling back to client IP for anonymous requests):

- **Default**: 100 requests/minute per key, applied globally.
- **`POST /onboard`**: 10 requests/minute per key (document-upload endpoint).

A `429 Too Many Requests` response is returned when a limit is exceeded.

## Routes

### Onboarding (`/onboard`)

- `POST /onboard` — multipart form: `application` (JSON `LoanApplication`)
  + `documents` (uploaded images). Runs the full `OnboardingPipeline` and
  returns an `OnboardingDecision`. Rate-limited to 10/min.

### Human Review (`/review`)

- `GET /review/queue` — paginated, filterable review queue
- `GET /review/queue/summary` — queue summary stats
- `GET /review/{case_id}` — case detail
- `POST /review/{case_id}/assign` — assign a case to a reviewer
- `POST /review/{case_id}/override` — submit a reviewer override
- `GET /review/{case_id}/overrides` — override history

### Audit (`/audit`)

- `GET /audit/{application_id}/explainability` — SHAP/LIME/copilot
  explainability result for an application
- `GET /audit/{application_id}/retraining-data` — feature snapshots +
  overrides collected for retraining

### Evidence (`/evidence`)

- `GET /evidence/{application_id}/chains` — all `EvidenceChain`s
  (identity, income, affordability, overall decision) for an application,
  requires `audit:read`
- `GET /evidence/{application_id}/source/{field_name}` — `SourceLocation`
  (document ID, bounding box, extraction method/model version) for a single
  extracted field, for UI document-overlay traceability. Requires
  `audit:read`.

### Admin (`/admin`)

All endpoints require `admin:read` (GET) or `admin:write` (POST), backed by
`MLOpsProcessor`:

- `GET /admin/models` — production model registry
- `POST /admin/models/{model_name}/promote` — promote a model version to a
  new `ModelStage`, gated on `PROMOTION_GATES` metric thresholds
- `GET /admin/drift-alerts` — drift alerts (optional `?acknowledged=`)
- `POST /admin/drift-alerts/{alert_id}/acknowledge` — acknowledge an alert
- `GET /admin/retraining-triggers` — retraining trigger history
- `POST /admin/retraining/{model_name}/trigger` — manually trigger scheduled
  retraining
- `GET /admin/feature-views` — Feast feature view definitions
- `GET /admin/api-keys` — redacted view of configured API keys (user_id +
  role only)

### Compliance (`/compliance`)

DPDP, RBI DLG, and PMLA/AML endpoints (see `COMPLIANCE.md` for the
regulatory mapping):

- `POST /compliance/consent`, `GET /compliance/consent/{application_id}`,
  `POST /compliance/consent/{application_id}/withdraw`
- `DELETE /compliance/applications/{application_id}/personal-data`,
  `GET /compliance/applications/{application_id}/data-summary`
- `POST /compliance/kfs/{application_id}`,
  `POST /compliance/kfs/{application_id}/disclose`,
  `POST /compliance/kfs/{application_id}/accept`
- `POST /compliance/cooling-off/{application_id}`,
  `POST /compliance/cooling-off/{application_id}/cancel`
- `POST /compliance/aml/{application_id}` — PEP/AML check
- `GET /compliance/data-residency` — verifies configured infra endpoints
  resolve to India region

### UI (`/ui`)

Server-rendered (Jinja2) human-review UI: `/ui/queue`,
`/ui/review/{case_id}`, `POST /ui/review/{case_id}/override`.

### Health

- `GET /health` — liveness
- `GET /health/ready` — dependency readiness (postgresql, minio, opensearch,
  neo4j, redis, kafka)
- `GET /health/live` — liveness
