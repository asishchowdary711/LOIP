# COMPLIANCE

How LOIP implements RBI, DPDP, and PMLA/AML obligations. Implementation
lives in `domains/compliance/` (`ComplianceProcessor`) and is exposed via
`/compliance/*` routes (see `API.md`).

## DPDP Act 2023

| Requirement | Implementation |
|---|---|
| Explicit consent before processing | `POST /compliance/consent` records a `ConsentRecord` (application_id, purpose, consent_version, document_hash) |
| Purpose limitation | `ComplianceProcessor.verify_consent(application_id, purpose)` checked before bureau/KYC API calls |
| Data deletion right | `DELETE /compliance/applications/{id}/personal-data` — PII fields listed and zeroed, documents marked deleted, `DataDeletionRequest` recorded with an audit tombstone UUID |
| Data principal access | `GET /compliance/applications/{id}/data-summary` |
| Consent withdrawal | `POST /compliance/consent/{id}/withdraw` — sets `ConsentStatus.WITHDRAWN`, blocks further processing |

## PII Protection

`ComplianceProcessor.mask_pii_in_text(text)` returns `(masked_text,
PIIMaskingResult)`:

- **`mock_mode=True` (default)**: regex-based masking for PAN
  (`ABCDE***F`), Aadhaar (`**** **** 1234`), phone (`******1234`), and email
  (`r***@example.com`). Fast, dependency-free, used by all existing tests.
- **`mock_mode=False`**: Microsoft Presidio (`AnalyzerEngine` +
  `AnonymizerEngine`). Custom `PatternRecognizer`s register `PAN_NUMBER` and
  `AADHAAR_NUMBER` entity types using the same regexes as the mock path;
  Presidio's built-in recognizers cover `PHONE_NUMBER`, `EMAIL_ADDRESS`,
  `PERSON`, and `LOCATION` (name/address, per build plan §9.3). Custom
  anonymizer operators reuse the same `mask_pan`/`mask_aadhaar`/
  `mask_phone`/`mask_email` static methods so masked output format is
  identical between the two modes. If `presidio-analyzer`/
  `presidio-anonymizer` (or their spaCy model dependency) aren't installed,
  initialization falls back to `mock_mode=True` automatically with a
  warning logged.

Not yet implemented: PostgreSQL column-level encryption (pgcrypto) for PII
fields, and routing audit-log writes to OpenSearch through the masking
layer.

## PMLA / AML

- **PEP screening**: `ComplianceProcessor.screen_pep(application_id,
  applicant_name, pan)` — in mock mode always returns `PEPStatus.CLEAR`; the
  real path (government PEP list lookup) is not yet implemented.
- **High-value loans**: `HIGH_VALUE_THRESHOLD = 5_000_000` (₹50L) —
  `check_aml()` flags loans above this threshold for enhanced due diligence.
- **SAR queue**: `POST /compliance/aml/{application_id}` runs
  `check_aml(application_id, loan_amount, fraud_score)` returning an
  `AMLCheckResult` with `AMLRiskLevel`.

## RBI Digital Lending Guidelines 2022

Implemented in `web/routes/consent.py` + `ComplianceProcessor`:

| Requirement | Implementation |
|---|---|
| KFS disclosure | `POST /compliance/kfs/{id}` generates a `KeyFactStatement` (APR, processing fee, tenure, EMI — `PROCESSING_FEE_PCT = 0.02`); `/disclose` and `/accept` transition `KFSStatus` |
| Cooling-off period | `POST /compliance/cooling-off/{id}` starts a 3-day (`COOLING_OFF_DAYS`) window; `/cancel` transitions `CancellationStatus.CANCELLED` |
| NACH mandate | `NACHMandate` schema exists; mandate-reference persistence not yet wired into the onboarding pipeline |
| LSP disclosure | Included as a field on `KeyFactStatement` |
| Disbursement account cross-check | Not yet implemented |

## Data residency

`ComplianceProcessor.check_data_residency(endpoints: dict[str, str])` checks
each configured infrastructure endpoint against India-region patterns
(`ap-south`, `india`, `mumbai`, `hyderabad`, `chennai`, `localhost`,
`127.0.0.1` — localhost stands in for India-region infra in dev). Exposed
via `GET /compliance/data-residency`.

This check is enforced in CI (`tests/compliance/test_data_residency.py`,
run as part of `.github/workflows/ci.yml`'s `test` job) — a non-India
endpoint added to the production endpoint set will fail the test suite.

## RBAC

6 roles (`admin`, `manager`, `senior_reviewer`, `reviewer`, `api_consumer`,
`compliance_officer`) defined in `web/auth.py`. See `API.md` for the
permission matrix.

## Security CI gates

`.github/workflows/ci.yml` runs `pip-audit`, `bandit`, and `safety` on every
push/PR to `main` (build plan §9.6). These are currently **blocking** — a
new vulnerable dependency or flagged code pattern fails CI. A full OWASP
Top 10 review has not yet been performed.
