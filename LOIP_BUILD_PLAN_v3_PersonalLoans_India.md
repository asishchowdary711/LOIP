# LOIP — Loan Onboarding Intelligence Platform
## Personal Loans · India Only
### Build Plan v3 — Post-Review Corrections Applied

> **Scope lock:** This plan covers **personal loans (unsecured consumer credit) in India only**.
> Mortgage, LAP, vehicle loans, and business loans are out of scope.
> All document types, regulatory references, income norms, and decisioning thresholds are
> calibrated to this segment.

> **Key changes from v2:**
> 1. Scope narrowed to personal loans India — mortgage content removed, India-specific KYC, income, and affordability norms applied
> 2. MIDV-500/2020 role corrected: European/Russian ID corpus used for OCR robustness only; Indian KYC training data comes exclusively from custom generators
> 3. Annotation pipeline added as a first-class Phase 0 deliverable — bridges generator JSON metadata to LayoutLMv3/Donut training format
> 4. RVL-CDIP/FUNSD described accurately as backbone pre-training only (not Indian document classifiers)
> 5. DocVQA acceptance threshold defined: ANLS ≥ 0.75 required before Qwen2.5-VL goes to production extraction
> 6. India regulatory layer added: RBI KYC Master Direction, Digital Lending Guidelines 2022, DPDP Act 2023, PMLA
> 7. Official government verification APIs added: UIDAI Aadhaar OTP eKYC, NSDL/UTI PAN verification, DigiLocker, CIBIL/Experian/Equifax India
> 8. Video KYC (V-CIP) added per RBI January 2020 circular
> 9. FOIR as primary affordability metric (Indian lending standard)
> 10. CIBIL score hard gate added to decisioning

---

## 1. India Personal Loan — Domain Context

### 1.1 Document Universe (In Scope)

| Category | Documents | Mandatory |
|---|---|---|
| **Identity (KYC OVD)** | PAN Card, Aadhaar Card | Both mandatory per RBI KYC norms |
| **Identity (optional OVD)** | Passport, Driving Licence | Supplement only |
| **Address Proof** | Aadhaar (address field), utility bill, rent agreement | One required |
| **Income — Salaried** | Salary slips (last 3 months), bank statements (last 6 months), Form 16 (latest FY) | All three preferred |
| **Income — Self-Employed** | ITR (last 2 years), bank statements (last 12 months), GST returns (last 4 quarters) | All three preferred |
| **Employment** | Offer letter / employment certificate | Optional but scored |

### 1.2 Personal Loan Parameters (India)

| Parameter | Typical Range |
|---|---|
| Loan amount | ₹50,000 – ₹40,00,000 |
| Tenure | 12 – 60 months |
| Interest rate | 10.5% – 24% p.a. (depends on credit profile) |
| Processing fee | 0.5% – 3% of loan amount |
| Minimum CIBIL score | 700 (< 650 → auto-reject at most lenders) |
| FOIR ceiling (salaried) | ≤ 50–55% of gross monthly income |
| Minimum net monthly income | ₹20,000 – ₹25,000 (lender-configurable) |
| Employment vintage | ≥ 6 months in current job (salaried) |

### 1.3 Employment Risk Tiers (India Salaried Context)

| Tier | Category | Risk Weight |
|---|---|---|
| 1 | PSU / Central / State Government | Lowest |
| 2 | Listed MNC / Fortune 500 India subsidiary | Low |
| 3 | Large listed Indian private company | Medium-Low |
| 4 | Mid-size private company | Medium |
| 5 | Startup / unlisted SME | High |

---

## 2. Regulatory Compliance Framework

Non-negotiable compliance constraints that shape every domain's design.

| Regulation | Implication |
|---|---|
| **RBI Master Direction — KYC (2016, updated 2022)** | Aadhaar-based OTP eKYC is valid; PAN mandatory for loans; Video-based CIP (V-CIP) required for fully digital onboarding without branch visit |
| **RBI Digital Lending Guidelines (Sept 2022)** | KFS (Key Fact Statement) with APR disclosed upfront; EMI debit only via NACH mandate; loan disbursement only to borrower's bank account |
| **Prevention of Money Laundering Act (PMLA)** | Enhanced due diligence for loans above ₹50L; Politically Exposed Person (PEP) screening required |
| **DPDP Act 2023 (effective 2024)** | Explicit consent before processing Aadhaar/PAN/financial data; data deletion rights; purpose limitation; data principal rights |
| **RBI Data Localization** | All financial data must be stored on servers located in India; cross-border transfer of payment/credit data prohibited |
| **Credit Information Companies (CIC) Regulations** | Credit bureau pull requires explicit borrower consent; must report to at least one CIC; adverse data reporting rules apply |

---

## 3. Requirements Traceability

### 3.1 Problem Statement & Definition of Done

| Requirement | Delivered By | Phase |
|---|---|---|
| Verify borrower identity — extract from ID docs, cross-check vs application | Phase 1b: Identity Trust (BGE-M3 entity matching PAN ↔ Aadhaar ↔ application; UIDAI/NSDL API verification) | Phase 1, Weeks 3-4 |
| Reconstruct true income from messy documents | Phase 1c: Income Intelligence (salary slip + bank statement + Form 16/ITR reconciliation with source-trust weighting) | Phase 1, Weeks 5-6 |
| Compute defensible DTI / FOIR | Phase 1d: Affordability Intelligence (FOIR primary, DTI secondary; derived from verified income + bank statement obligations) | Phase 1, Weeks 5-6 |
| Flag tampering / mismatch | Phase 1b anomaly flags + Phase 1c income anomaly flags + Phase 2 full fraud intelligence | Phases 1-2 |
| Overall onboarding risk score | Phase 1e: Risk Decisioning (hard rules gate → CIBIL gate → XGBoost ensemble) | Phase 1, Weeks 7-8 |
| Approve / Review / Reject with reason codes | Phase 1e: Decision engine with reason codes catalog | Phase 1, Weeks 7-8 |
| Every figure traced to source | Traceability Contract: `EvidenceChain` + `SourceLocation` on every output field, enforced from Phase 0 | All phases |

### 3.2 DATA GUIDANCE — Corrected Mapping

| DATA GUIDANCE Item | Actual Role in This Plan | Phase | Correction vs v2 |
|---|---|---|---|
| **MIDV-500 / MIDV-2020** | OCR robustness testing only — diverse capture conditions (angles, blur, shadows, lighting) for preprocessing pipeline validation. NOT used for Indian document classification training (MIDV contains European/Russian IDs, not PAN/Aadhaar). | Phase 0 + Phase 1a | ✅ Corrected: v2 incorrectly described these as Indian document training data |
| **Synthetic pay-stub generator** | `scripts/generators/generate_salary_slip.py` — primary income training and test data for salaried segment | Phase 0, Weeks 1-2 | No change — was correct |
| **Synthetic bank-statement generator** | `scripts/generators/generate_bank_statement.py` — primary affordability training and test data | Phase 0, Weeks 1-2 | No change — was correct |
| **RVL-CDIP** | LayoutLMv3 backbone pre-training for layout understanding transfer. 16 generic document categories provide spatial/structural features. NOT a substitute for Indian document fine-tuning data (which comes from the annotation pipeline). | Phase 0 + Phase 1a | ✅ Corrected: v2 overstated as "Indian document classifier" |
| **FUNSD** | Donut backbone pre-training for form key-value understanding on 199 English forms. NOT fine-tuning for Indian salary slips/bank statements — those require the annotation pipeline output. | Phase 0 + Phase 1a | ✅ Corrected: v2 implied FUNSD annotations cover Indian documents |
| **DocVQA** | Qwen2.5-VL acceptance benchmark. Deployment gates on ANLS ≥ 0.75 on DocVQA subset before any production extraction. Used for validation, not training. | Phase 1a | ✅ Corrected: threshold now explicit; v2 had no acceptance criterion |
| **"Generating realistic test documents is part of the challenge"** | 6 generators with `tamper_type` parameter + `generate_case.py` multi-document case composer + annotation pipeline that converts generator output to model training data | Phase 0, Weeks 1-2 | Enhanced: annotation pipeline is the new deliverable that closes the v2 gap |

### 3.3 Solution Hint

| Hint | How Addressed |
|---|---|
| "OCR is the easy part" | OCR is Phase 1a sub-component only; 5 of 8 phases address reconciliation, fraud signals, and auditability |
| "Reconciling conflicting messy documents" | Phase 1c reconciles salary slip, bank statement, Form 16, ITR via source-trust weighting (Form 16 > ITR > bank > salary slip); Phase 1b reconciles identity fields across PAN, Aadhaar, application |
| "Fraud/anomaly signals with reasoning" | Phase 1b/c hard-rule anomaly flags → Phase 2 graph fraud + behavioral anomaly → Phase 3 SHAP + Qwen3 reviewer copilot narratives |
| "Keeping affordability figure auditable to source" | `AffordabilityResult.income_evidence: list[EvidenceChain]` traces every figure through `ExtractedField.source` to a bounding box on a stored document |

---

## 4. Traceability Contract

Defined once, enforced on every domain output.

```python
# schemas/evidence.py

class SourceLocation(BaseModel):
    document_id: str             # UUID → MinIO stored document
    document_type: str           # "pan", "aadhaar", "salary_slip", "bank_statement",
                                 # "form16", "itr", "gst_return", "offer_letter"
    is_synthetic: bool = False   # True for generated test data; suppresses prod audit log
    page_number: int | None
    coordinates: dict | None     # {"x0": int, "y0": int, "x1": int, "y1": int}
                                 # Normalized 0-1000 (LayoutLMv3 convention)
    extraction_method: str       # "paddleocr", "surya", "qwen2.5-vl", "donut",
                                 # "uidai_api", "nsdl_api", "cibil_api", "human_entry"
    model_version: str           # e.g. "paddleocr-4.0", "qwen2.5-vl-7b-v1"

class ExtractedField(BaseModel):
    field_name: str              # "pan_number", "annual_income", "employer_name", etc.
    raw_value: str
    normalized_value: str | None
    confidence: float            # 0.0 – 1.0
    source: SourceLocation
    verified_by: list[str] = [] # verification model IDs or API names that confirmed value

class EvidenceChain(BaseModel):
    claim: str                   # "applicant_annual_income = ₹12,00,000"
    supporting: list[ExtractedField]
    contradicting: list[ExtractedField]
    reconciled_value: str | float
    reconciliation_method: str   # "source_trust_weighted", "majority_vote",
                                 # "highest_confidence", "api_authoritative"
    confidence: float
```

All domain outputs (identity, income, affordability, fraud, risk) are wrappers around evidence chains. API-authoritative sources (UIDAI, NSDL, CIBIL) use `reconciliation_method = "api_authoritative"` and automatically win over document-extracted values.

---

## 5. Phase 0: Foundation + Data Assets + Annotation Pipeline (Weeks 1-2)

### 5.1 Infrastructure

Docker Compose services:

| Service | Purpose |
|---|---|
| PostgreSQL 16 | Evidence repository, application data, consent records |
| MinIO | Document storage (one bucket per doc type), model artifacts, annotation data |
| OpenSearch | Full-text search, audit logs (1-year retention), SHAP storage |
| Neo4j 5 | Identity graph (Person, PAN, Aadhaar, Phone, Email, Device, Employer, Bank Account) |
| Kafka + Zookeeper | Async event pipeline between domains |
| Redis 7 | Rate limiting, session cache, Feast online feature store |
| MLflow | Experiment tracking, model registry (staging → production promotion) |
| Evidently AI | Data/model/target drift monitoring config |
| Prometheus + Grafana | Metrics, dashboards, alerting |
| vLLM / Ollama | Qwen2.5-VL-7B and Qwen3-32B local inference |

> **Data residency:** All services must be deployed on India-region infrastructure (e.g., AWS ap-south-1 Mumbai, Azure India Central, or on-premise). RBI data localization prohibits storing financial data outside India.

### 5.2 Data Assets — Accurate Role Descriptions

| Asset | Source | Actual Role | What It Does NOT Do |
|---|---|---|---|
| MIDV-500 | Public — 500 images of mock passports, DLs (primarily European/Russian docs) | OCR preprocessing robustness test: deskew, deblur, adaptive threshold tested against this corpus | Does NOT train Indian PAN/Aadhaar classifiers — wrong document domain |
| MIDV-2020 | Extended MIDV — more doc types, lighting/angle variations | Additional OCR robustness test cases; preprocessing edge cases | Same as above |
| RVL-CDIP | 400K document images in 16 generic categories (letters, memos, invoices, etc.) | LayoutLMv3 backbone pre-training: spatial layout features, column/table understanding transfer | Does NOT produce an Indian financial document classifier out of the box |
| FUNSD | 199 annotated English form images with key-value pairs | Donut backbone pre-training: form field structure, key-value spatial relationships | Does NOT cover Indian salary slip / bank statement layouts; Indian training data comes from annotation pipeline |
| DocVQA | 50K document pages with question-answer pairs | Qwen2.5-VL **validation benchmark only**: ANLS ≥ 0.75 required before production deployment | Not used for fine-tuning |

**MIDV download note:** MIDV-500 and MIDV-2020 are academic datasets. The download script should verify checksums and log which specific document nationality/type distributions are present to avoid silently training on mismatched data.

### 5.3 Indian KYC Document Generators

| Generator | Output | Ground-Truth Fields |
|---|---|---|
| `generate_pan_card.py` | PNG image + JSON metadata | PAN number, full name, father's name, date of birth, signature region flag |
| `generate_aadhaar.py` | PNG image (front + back) + JSON | Aadhaar number (masked for display), full name, DOB, gender, address (door, street, locality, city, state, pincode) |
| `generate_salary_slip.py` | PDF + JSON | Employer name, employer type (tier 1-5), employee name, employee PAN, UAN, basic, HRA, conveyance, special allowance, PF, PT, TDS, gross, net, month, year |
| `generate_bank_statement.py` | PDF + JSON | Bank name, account number, account holder name, period, transactions (date, narration, credit, debit, balance), opening/closing balance |
| `generate_form16.py` | PDF + JSON | Employer TAN, employee PAN, assessment year, gross salary, all allowances, deductions (80C, 80D, 80E, 80G), taxable income, TDS deducted |
| `generate_itr.py` | PDF + JSON | PAN, assessment year, ITR type (ITR-1 Sahaj for salaried), gross total income, deductions, total income, tax payable, refund |
| `generate_gst_return.py` | PDF + JSON | GSTIN, turnover (B2B, B2C), tax period, IGST, CGST, SGST — for self-employed segment |
| `generate_offer_letter.py` | PDF + JSON | Company name, company tier, CTC, joining date, designation, location |

**Tamper modes (all generators accept `--tamper-type`):**

| Mode | Effect |
|---|---|
| `income_inflation` | Salary slip gross inflated 30–80%; bank credits not adjusted (creates detectable mismatch) |
| `income_deflation` | Bank statement salary credits hidden or reduced |
| `identity_mismatch` | Name differs between PAN and Aadhaar by one word, transposition, or extra initial |
| `dob_mismatch` | DOB differs between PAN and Aadhaar by 1–3 years |
| `employer_mismatch` | Employer name on salary slip differs from application by abbreviation or word order |
| `pan_mismatch` | PAN on salary slip differs from PAN card by one character |
| `synthetic_identity` | PAN + Aadhaar belong to different persons (different address states) |
| `document_forgery` | Metadata planted: created_by = "Adobe Photoshop", future creation date |
| `missing_fields` | Salary slip missing PF, TDS, or UAN fields |
| `employer_shell` | Employer CIN does not exist in MCA21 database |

### 5.4 Annotation Pipeline — NEW: Critical Missing Piece from v2

This pipeline bridges the gap between generator output (documents + JSON metadata) and the annotated training format required by LayoutLMv3 and Donut. Without this, the document understanding models cannot learn Indian-specific field layouts.

**Gap being closed:** Generators produce `{field_name: value}` JSON. LayoutLMv3 training requires `{text_token, bounding_box_coordinates, BIO_label}` per word. Donut training requires `{question, answer}` pairs grounded in document regions. The annotation pipeline produces both from generator output.

```python
# scripts/annotate/generate_annotations.py
"""
Input:
  - document_image: PNG rendered from generator (or PDF page)
  - generator_metadata: JSON { "pan_number": "ABCDE1234F", "full_name": "Rajesh Kumar", ... }

Output (per document):
  - layoutlmv3_annotation.json  → FUNSD-format with normalized bounding boxes (0-1000)
  - donut_annotation.json       → { "gt_parse": { "pan_number": "...", "full_name": "..." } }

Steps:
  1. Run PaddleOCR on document_image → word-level bounding boxes + text
  2. For each ground-truth field value in generator_metadata:
       a. Fuzzy-match against OCR tokens (Levenshtein distance ≤ 2 for names)
       b. Exact-match for PAN numbers, Aadhaar numbers, amounts
  3. Assign BIO labels to matched token spans:
       B-FULL_NAME, I-FULL_NAME, B-PAN_NUMBER, B-EMPLOYER_NAME, etc.
  4. Unmatched tokens → label: "OTHER"
  5. Normalize bounding boxes: (pixel_coord / image_dimension) * 1000
  6. Emit FUNSD-format JSON and Donut GT JSON
"""
```

**Label schema per document type:**

| Document | BIO Labels |
|---|---|
| PAN Card | `PAN_NUMBER`, `FULL_NAME`, `FATHER_NAME`, `DATE_OF_BIRTH` |
| Aadhaar Card | `AADHAAR_NUMBER`, `FULL_NAME`, `DATE_OF_BIRTH`, `GENDER`, `ADDRESS_LINE`, `PINCODE` |
| Salary Slip | `EMPLOYER_NAME`, `EMPLOYEE_NAME`, `EMPLOYEE_PAN`, `UAN`, `GROSS_PAY`, `NET_PAY`, `BASIC`, `HRA`, `PF_DEDUCTION`, `TDS_DEDUCTION`, `PAY_MONTH`, `PAY_YEAR` |
| Bank Statement | `BANK_NAME`, `ACCOUNT_NUMBER`, `ACCOUNT_HOLDER_NAME`, `PERIOD_START`, `PERIOD_END`, `OPENING_BALANCE`, `CLOSING_BALANCE`, `TXN_DATE`, `TXN_NARRATION`, `TXN_CREDIT`, `TXN_DEBIT` |
| Form 16 | `EMPLOYER_TAN`, `EMPLOYEE_PAN`, `ASSESSMENT_YEAR`, `GROSS_SALARY`, `TAXABLE_INCOME`, `TDS_DEDUCTED` |

**Training volume targets (minimum before Phase 1a model training):**

| Document Type | Clean Samples | Tampered Samples | Total |
|---|---|---|---|
| PAN Card | 1,000 | 500 | 1,500 |
| Aadhaar Card | 1,000 | 500 | 1,500 |
| Salary Slip | 2,000 | 1,000 | 3,000 |
| Bank Statement | 2,000 | 1,000 | 3,000 |
| Form 16 | 500 | 250 | 750 |
| ITR | 500 | 250 | 750 |
| **Total** | **7,000** | **3,500** | **10,500** |

> **⚠️ Scope update (accepted):** the full **10,500-doc corpus is NOT required**.
> A **25-document mixed sample** (`loip/data/annotation_sample25/`, ~80.5% avg
> field-match across all 6 doc types) is the agreed annotation set and is
> sufficient to validate the annotation pipeline end-to-end. The volume targets
> above are retained for reference only. See `loip/docs/DATA_GUIDANCE_NOTES.md`
> and `loip/data/manifest.json`.

### 5.5 Phase 0 Deliverables

- `docker-compose.yml` with all services + India-region configuration note
- Database migrations (Alembic) including consent and DPDP records tables
- MinIO bucket policies (one bucket per doc type + evidence bucket + model bucket + annotation bucket)
- Neo4j constraints (PAN, Aadhaar, Phone, Email uniqueness)
- Kafka topics (one per domain event)
- MIDV-500, MIDV-2020 downloaded + OCR robustness test suite run against them (pass/fail per preprocessing step)
- RVL-CDIP, FUNSD, DocVQA downloaded and indexed
- All 8 generators implemented as CLI scripts in `scripts/generators/`
- Annotation pipeline implemented: `scripts/annotate/generate_annotations.py`
- 10,500 annotated training samples generated (per table above)
- Test harness: validates each generator's output is OCR-parseable by PaddleOCR with confidence > 0.85
- Case composer: `generate_case.py --tamper-type income_inflation --segment salaried --output ./test_cases/case_001/`
- `scripts/download_datasets.py` with checksum verification + MIDV distribution report

---

## 6. Phase 1: Core DoD Pipeline (Weeks 3-8)

**Goal:** End-to-end prototype: identity docs + income docs + application → full DoD output. Face verification, liveness, V-KYC, graph fraud deferred to Phase 2.

### 6.1 Phase 1a — Document Intelligence (Weeks 3-4)

**Supported document types (Phase 1 scope):**
- PAN Card, Aadhaar Card (identity)
- Salary Slip, Bank Statement (income — salaried segment only in Phase 1)

**Document Classification (LayoutLMv3):**

| Training Data | Role |
|---|---|
| RVL-CDIP (400K) | Backbone pre-training: spatial layout features, structural understanding |
| Annotation pipeline output — Indian docs (10,500) | Fine-tuning: Indian document classes and field positions |
| MIDV-500/2020 | Not used for classification training |

- 5 classes: PAN, Aadhaar, Salary Slip, Bank Statement, Reject/Unknown
- Confidence threshold: ≥ 0.85 to classify; else flag for human review
- Evaluation: held-out 20% of annotation pipeline output (not seen during fine-tuning)

**OCR Pipeline:**
```python
def preprocess_image(image: np.ndarray) -> np.ndarray:
    # Step 1: Deskew — correct rotation up to ±15° (Hough transform)
    # Step 2: Deblur — Wiener filter or Laplacian sharpening
    # Step 3: Adaptive thresholding — Sauvola method (better than global for uneven lighting)
    # Step 4: Denoise — bilateral filter (preserves edges)
    # Step 5: Border crop — remove scan borders
    return preprocessed

def ocr_document(image: np.ndarray) -> OCRResult:
    cleaned = preprocess_image(image)
    primary = PaddleOCR.extract(cleaned)             # always runs
    secondary = SuryaOCR.extract(cleaned) if primary.confidence < 0.9 else None
    if secondary and abs(primary.confidence - secondary.confidence) > 0.15:
        return ConflictResult(primary, secondary)    # raises verification flag
    return primary
```

> **MIDV-500/2020 role here:** These datasets are used only to stress-test the preprocessing pipeline (Steps 1-4) against diverse capture conditions — different angles, blur levels, lighting shadows found in scanned Indian documents. They are not used to train the classifier.

**Field Extraction (Qwen2.5-VL via vLLM, fine-tuned on annotation pipeline output):**

Pre-deployment gate: ANLS score ≥ 0.75 on a held-out DocVQA subset before extraction is used in production. This threshold is hard-gated in `scripts/evaluate_qwen_docvqa.py`.

```python
# ANLS evaluation before deploying extraction model
def evaluate_qwen_anls(model, docvqa_held_out: list[QAPair]) -> float:
    scores = []
    for qa in docvqa_held_out:
        pred = model.extract(qa.document_image, qa.question)
        scores.append(anls_score(pred, qa.answer))  # ANLS: edit-distance normalized
    anls = sum(scores) / len(scores)
    assert anls >= 0.75, f"Qwen2.5-VL ANLS {anls:.3f} below 0.75 gate — do not deploy"
    return anls
```

**Field extraction targets:**

| Document | Fields |
|---|---|
| PAN Card | PAN number, full name, father's name, date of birth |
| Aadhaar Card | Aadhaar number, full name, DOB, gender, full address, pincode |
| Salary Slip | Employer name, employee name, employee PAN, UAN, basic, HRA, gross pay, net pay, PF deduction, TDS deduction, month, year |
| Bank Statement | Bank name, account number, account holder name, period, all transactions (date, narration, credit, debit, balance), opening/closing balance |

**Donut fallback:**
- Fine-tuned on FUNSD (backbone) + annotation pipeline Indian salary slip/bank statement annotations
- Triggered when Qwen2.5-VL confidence < 0.7 on structured-form documents
- Provides cross-check on structured tabular fields (salary components, bank transaction rows)

### 6.2 Phase 1b — Identity Trust Lite (Weeks 3-4, parallel)

**Deferred:** Face verification, liveness detection, identity graph (Phase 2)

**Step 1 — Official API Verification (authoritative, wins over document extraction):**

```python
async def verify_pan_official(pan_number: str, full_name: str, dob: str) -> APIVerificationResult:
    # NSDL / UTI PAN verification API
    # Returns: name_match (bool), status (active/inactive/invalid), name_on_pan
    response = await nsdl_client.verify(pan=pan_number, name=full_name, dob=dob)
    return APIVerificationResult(
        source="nsdl_api",
        matched=response.name_match,
        status=response.status,
        evidence=SourceLocation(extraction_method="nsdl_api", document_type="pan")
    )

async def verify_aadhaar_otp(aadhaar_number: str, mobile_otp: str) -> APIVerificationResult:
    # UIDAI Aadhaar OTP eKYC
    # Requires borrower's mobile OTP (linked to Aadhaar)
    # Returns: verified (bool), demographic data (name, dob, gender, address) — only what borrower consents to share
    # DPDP Act compliance: consent captured before this API call
    response = await uidai_client.verify_otp(aadhaar=aadhaar_number, otp=mobile_otp)
    return APIVerificationResult(source="uidai_api", matched=response.verified, ...)
```

> **DPDP Act 2023 compliance:** Explicit consent for Aadhaar processing must be captured and stored before this call. Consent record stored in `consent_records` table with `consent_version`, `consented_at`, `purpose = "kyc_verification"`, `document_hash`.

**Step 2 — Cross-Document Entity Matching (BGE-M3):**

```python
def verify_identity(application: Application, extracted: dict, api_results: dict) -> IdentityVerificationResult:
    checks = [
        # API-verified values take precedence (api_authoritative in EvidenceChain)
        match("pan_number",   [extracted["pan"], api_results["nsdl"], application]),
        match("full_name",    [extracted["pan"], extracted["aadhaar"], api_results["uidai"], application]),
        match("date_of_birth",[extracted["pan"], extracted["aadhaar"], api_results["uidai"], application]),
        match("address",      [extracted["aadhaar"], api_results["uidai"], application]),
        match("father_name",  [extracted["pan"], application]),
    ]
    # Similarity thresholds:
    # PAN number: exact match required (< 1.0 → REJECT)
    # Name: BGE-M3 cosine ≥ 0.85 (accounts for spelling variants, missing initials)
    # DOB: exact match required
    # Address: BGE-M3 cosine ≥ 0.70 (addresses vary in format)
```

**Tamper/forgery flags (Phase 1 hard rules):**

| Flag | Trigger |
|---|---|
| `pan_format_invalid` | PAN doesn't match regex `[A-Z]{5}[0-9]{4}[A-Z]` |
| `pan_nsdl_inactive` | NSDL returns status ≠ "active" |
| `aadhaar_format_invalid` | Aadhaar ≠ 12 digits or fails Verhoeff checksum |
| `aadhaar_otp_failed` | UIDAI OTP verification failed |
| `name_pan_aadhaar_mismatch` | BGE-M3 similarity < 0.85 between PAN name and Aadhaar name |
| `dob_mismatch` | DOB differs between any two OVDs |
| `document_metadata_anomaly` | PDF created_by contains image editor (Photoshop, GIMP, etc.) or creation date is in the future |
| `address_state_mismatch` | Aadhaar address state inconsistent with application city (soft flag) |

### 6.3 Phase 1c — Income Intelligence (Weeks 5-6)

**Scope: Salaried segment only in Phase 1. Self-employed added in Phase 2.**

**Income Reconstruction Logic:**

```
monthly_income_salary_slip  = average(net_pay, last_3_slips)
monthly_income_bank         = median(recurring_salary_credits, last_6_months)
annual_income_form16        = gross_total_income from Form 16 (if provided)
annual_income_itr           = gross_total_income from ITR-1 (if provided)

# Source-trust weighting (India lending practice — tax documents most authoritative)
reconciled_annual_income = source_trust_weighted_average({
    (annual_income_form16,     trust=0.90),  # Tax-deducted at source — hardest to fake
    (annual_income_itr,        trust=0.85),  # Self-filed but NSDL-matched
    (annual_income_bank * 12,  trust=0.75),  # Actual bank credits — hard to fake but variable
    (monthly_income_salary_slip * 12, trust=0.65),  # Easiest to fabricate
})

verified_monthly_income = reconciled_annual_income / 12
```

**Salary credit detection in bank statement:**
```python
def detect_salary_credits(transactions: list[Transaction]) -> list[SalaryCredit]:
    # Identify recurring monthly credits as salary candidates
    # Rules:
    # 1. Credit narration contains: "SALARY", "SAL", "NEFT", employer name
    # 2. Amount consistency: CV < 0.15 across months (salary is stable)
    # 3. Recurrence: appears on similar date (±5 days) each month
    # 4. Frequency: at least 4 of last 6 months
    return [
        SalaryCredit(amount=txn.credit, date=txn.date, narration=txn.narration)
        for txn in transactions if matches_salary_pattern(txn)
    ]
```

**Anomaly flags:**

| Flag | Trigger |
|---|---|
| `salary_slip_vs_bank_mismatch` | Salary slip net pay vs. bank salary credit > 30% difference |
| `employer_name_mismatch` | Salary slip employer ≠ application employer (BGE-M3 < 0.80) |
| `pan_on_slip_mismatch` | PAN on salary slip ≠ PAN card |
| `uan_format_invalid` | UAN ≠ 12 digits |
| `salary_missing_mandatory_fields` | Salary slip missing any of: gross, net, PF deduction, TDS deduction |
| `income_below_rbi_minimum` | Verified income < ₹20,000/month (lender-configurable floor) |
| `bank_credit_volatility` | CV of monthly salary credits > 0.30 (irregular income) |
| `form16_itr_mismatch` | Form 16 gross salary vs. ITR gross income > 5% difference |
| `no_salary_credit_found` | Bank statement shows no qualifying salary credits in 6 months |

**Model:** XGBoost regressor predicting `true_income` from all extracted features. Trained on synthetic data where generator ground truth is the label. `income_confidence` output drives `EvidenceChain.confidence`.

### 6.4 Phase 1d — Affordability Intelligence (Weeks 5-6, parallel)

**Primary metric: FOIR (Fixed Obligation to Income Ratio)** — standard metric used by Indian banks and NBFCs. FOIR ≤ 50% is standard approval threshold for salaried borrowers.

**Obligation sources:**
- Existing EMIs: parsed from bank statement recurring fixed debits + declared in application
- Proposed EMI: computed from loan amount + tenure + indicative rate
- Credit card minimum due (if visible in bank statement)

**Affordability metrics:**

```python
proposed_emi = compute_emi(
    principal=application.loan_amount,
    annual_rate=indicative_rate,   # lender-configurable, e.g. 14% p.a.
    tenure_months=application.tenure_months
)

existing_obligations = sum(existing_emis) + credit_card_minimum_due
total_obligations = existing_obligations + proposed_emi

FOIR = min(total_obligations / verified_monthly_income, 1.0)
DTI  = FOIR  # same formula; DTI reported for completeness

disposable_income = verified_monthly_income - total_obligations - estimated_monthly_expenses
liquidity_score   = min(avg_monthly_balance / avg_monthly_debits, 1.0)  # last 3 months
financial_stress  = overdraft_count / total_months                        # last 6 months
cashflow_stability = 1.0 - min(cv_of_monthly_net_cashflow, 1.0)
```

**Estimated monthly expenses:** ₹15,000 flat (configurable) as proxy for living expenses not visible in statement.

**Hard FOIR gate:**

| FOIR | Decision |
|---|---|
| ≤ 0.50 | Pass (salaried) |
| 0.51 – 0.60 | Review (marginal; factor in employment tier) |
| > 0.60 | Reject: `foir_exceeded` |

**Output:**

```python
class AffordabilityResult(BaseModel):
    verified_monthly_income: float
    income_confidence: float
    income_evidence: list[EvidenceChain]
    existing_obligations: float
    proposed_emi: float
    total_obligations: float
    foir: float
    dti: float
    disposable_income: float
    liquidity_score: float
    cashflow_stability: float
    financial_stress_score: float
    affordability_score: float      # 0.0 - 1.0 from LightGBM
    affordability_confidence: float
    anomaly_flags: list[str]
```

### 6.5 Phase 1e — Risk Decisioning (Weeks 7-8)

**Input streams:**
- Identity result (Phase 1b): identity_confidence, mismatches, tamper_flags
- Income result (Phase 1c): verified_income, income_confidence, anomaly_flags
- Affordability result (Phase 1d): FOIR, DTI, cashflow_stability, anomaly_flags
- CIBIL score (live API pull — consent required)

**CIBIL Integration:**

```python
async def pull_credit_bureau(pan: str, dob: str, name: str) -> CreditBureauResult:
    # CIBIL TransUnion API (primary)
    # Fallback: Experian India or Equifax India
    # Consent check: credit_bureau_consent must be True in consent_records before call
    response = await cibil_client.fetch_report(pan=pan, dob=dob, name=name)
    return CreditBureauResult(
        bureau="cibil",
        score=response.score,            # 300–900
        active_loans=response.active_loans_count,
        overdue_accounts=response.overdue_count,
        dpd_90_plus=response.dpd_90_plus_flag,  # Days-past-due ≥ 90 in last 24 months
        evidence=EvidenceChain(claim=f"cibil_score={response.score}", ...)
    )
```

**Decision engine:**

```python
def decide(identity: IdentityVerificationResult,
           income: IncomeResult,
           affordability: AffordabilityResult,
           bureau: CreditBureauResult,
           application: LoanApplication) -> OnboardingDecision:

    # Layer 1: Hard KYC rejects (non-negotiable, regulatory)
    if identity.identity_confidence < 0.30:
        return REJECT("identity_low_confidence", identity.mismatches)
    if "pan_nsdl_inactive" in identity.tamper_flags:
        return REJECT("pan_inactive_or_invalid")
    if "aadhaar_otp_failed" in identity.tamper_flags:
        return REJECT("aadhaar_verification_failed")
    if identity.has_flag("pan_format_invalid") or identity.has_flag("aadhaar_format_invalid"):
        return REJECT("kyc_document_invalid")

    # Layer 2: Hard credit rejects
    if bureau.score < 650:
        return REJECT("cibil_score_below_minimum", f"score={bureau.score}")
    if bureau.dpd_90_plus:
        return REJECT("dpd_90_plus_in_24_months")
    if bureau.overdue_accounts > 0:
        return REJECT("overdue_accounts_in_bureau")

    # Layer 3: Hard affordability rejects
    if affordability.foir > 0.60:
        return REJECT("foir_exceeded", f"foir={affordability.foir:.2f}")
    if income.verified_monthly_income < application.min_income_requirement:
        return REJECT("income_below_minimum")

    # Layer 4: Review triggers (soft flags)
    review_flags = []
    if identity.identity_confidence < 0.70:
        review_flags.append("identity_moderate_confidence")
    if affordability.foir > 0.50:
        review_flags.append(f"foir_marginal:{affordability.foir:.2f}")
    if income.anomaly_flags:
        review_flags.append(f"income_anomalies:{','.join(income.anomaly_flags)}")
    if affordability.anomaly_flags:
        review_flags.append(f"affordability_anomalies:{','.join(affordability.anomaly_flags)}")
    if bureau.score < 700:
        review_flags.append(f"cibil_marginal:{bureau.score}")
    if bureau.active_loans > 3:
        review_flags.append(f"multiple_active_loans:{bureau.active_loans}")
    if application.employment_tier >= 4:
        review_flags.append(f"employment_tier_high_risk:{application.employment_tier}")

    if review_flags:
        return REVIEW(review_flags)

    # Layer 5: Soft ML scoring
    score = xgboost_ensemble.predict({
        "identity_confidence": identity.identity_confidence,
        "income_confidence": income.income_confidence,
        "foir": affordability.foir,
        "cibil_score_normalized": (bureau.score - 300) / 600,
        "cashflow_stability": affordability.cashflow_stability,
        "employment_tier": application.employment_tier,
        "loan_to_income_ratio": application.loan_amount / (income.verified_monthly_income * 12),
    })
    if score >= 0.70:
        return APPROVE(score)
    elif score >= 0.40:
        return REVIEW(["borderline_score"])
    else:
        return REJECT("low_ensemble_score")
```

**Reason codes catalog:**

Identity: `identity_low_confidence`, `identity_mismatch_name`, `identity_mismatch_dob`, `pan_inactive_or_invalid`, `aadhaar_verification_failed`, `kyc_document_invalid`, `document_forgery_flag`

Credit: `cibil_score_below_minimum`, `dpd_90_plus_in_24_months`, `overdue_accounts_in_bureau`

Income: `income_below_minimum`, `income_inflation`, `income_mismatch_salary_vs_bank`, `employer_name_mismatch`, `bank_credit_not_found`

Affordability: `foir_exceeded`, `foir_marginal`, `cashflow_unstable`, `financial_stress_high`, `disposable_income_insufficient`

Risk: `borderline_score`, `multiple_active_loans`, `employment_tier_high_risk`, `manual_review_required`

### 6.6 Phase 1 Deliverables

- FastAPI endpoint: `POST /onboard` → accepts files + application JSON + consent tokens → returns `OnboardingDecision`
- Every output field traces through `EvidenceChain` to a source document or API
- NSDL/UIDAI/CIBIL API clients with mock stubs for testing
- DoD test suite passing (see Section 8)
- CLI: `python -m loip.evaluate --case-dir ./test_cases/case_001/`

---

## 7. Phase 2: Expand Depth — Self-Employed + Full Identity + Fraud (Weeks 9-12)

### 7.1 Additional Document Types

| Document | Extraction Additions |
|---|---|
| Passport | Passport number, nationality, expiry date, MRZ line parsing |
| Driving Licence | DL number, validity, transport category |
| Form 16 Part A + B | Full extraction; Part A from employer, Part B annexure |
| ITR-1 / ITR-4 (Sugam) | ITR-4 for self-employed (business income, presumptive income) |
| GST Returns (GSTR-1, GSTR-3B) | Turnover (B2B/B2C), tax period, IGST/CGST/SGST liability |

### 7.2 Self-Employed Income Module

Income reconstruction differs significantly from salaried:

```
income_source_itr_fy1       = adjusted_total_income from ITR-4 (FY n-1)
income_source_itr_fy2       = adjusted_total_income from ITR-4 (FY n-2)
income_source_gst_annual    = gross_turnover from GSTR-1 (annualized)
income_source_bank_credits  = total_annual_credits from bank (last 12 months)

# Self-employed trust weighting (ITR most authoritative)
reconciled_annual_income = source_trust_weighted_average({
    (income_source_itr_fy1, 0.90),
    (income_source_itr_fy2, 0.80),    # 2-year average preferred
    (income_source_gst_annual, 0.75),
    (income_source_bank_credits, 0.65),
})

# Apply standard profit margin assumption if only turnover available:
# net_income ≈ turnover * 0.25 (configurable; used if ITR unavailable)
```

### 7.3 Full Identity Trust

**Face Verification:**
- ArcFace: cosine similarity between ID document photo embedding and selfie embedding; match if ≥ 0.60
- InsightFace: secondary embedding; triggered if ArcFace confidence < 0.70
- Selfie upload: collected during application flow (mobile camera, not uploaded file)

**Liveness Detection (MiniFASNet):**
- Anti-spoofing on selfie input; score < 0.50 → `spoof_detected` flag → REJECT

**Video KYC — V-CIP (RBI January 2020 circular):**
- Required for fully digital personal loans without branch visit
- Process: live video call with bank agent, borrower shows OVD to camera, agent asks 2 random questions, geotagging required, explicit consent recorded
- Integration: WebRTC session + recording stored in MinIO (India-region)
- Completion required before loan disbursal for loans above ₹2 lakhs (configurable)

**Identity Graph (Neo4j):**

```
Nodes: Person, PAN, Aadhaar, Phone, Email, Device, Employer, BankAccount, Address
Edges: HAS_PAN, HAS_AADHAAR, HAS_PHONE, HAS_EMAIL, USES_DEVICE, WORKS_AT, HAS_ACCOUNT, LIVES_AT

Detection queries:
- Same device_fingerprint → multiple applications: `synthetic_identity_ring`
- Same phone → different PANs: `pan_farming`
- Same employer + different names: `employee_record_forgery`
- Aadhaar address state ≠ bank account state ≠ application city: `address_inconsistency_ring`
```

### 7.4 Fraud Intelligence

**Graph Fraud:**
- GraphSAGE: node classification (fraud / legitimate) trained on labeled synthetic ring cases
- Signals: shared device, shared phone, shared address across applications

**Behavioral Anomaly:**
- Isolation Forest: outlier detection on feature vectors (income ratios, document timing, session metadata)
- AutoEncoder: reconstruction error as anomaly score

**Document Forgery Rules (hard rules):**

| Rule | Signal |
|---|---|
| PDF metadata check | created_by contains Photoshop, GIMP, Inkscape, or any image editor |
| Creation date anomaly | Document creation date > today or > 30 days after stated document date |
| Font inconsistency | Mixed font families within a single text field (e.g., salary amount) |
| Image splicing | Bounding box aspect ratio of photo region inconsistent with template |
| MRZ checksum fail | Passport MRZ check digits fail ICAO Doc 9303 algorithm |
| PAN Verhoeff | Aadhaar number fails Verhoeff checksum |
| CIN verification | Employer CIN from salary slip cross-checked against MCA21 (if available via API) |

---

## 8. Phase 3: Explainability + Human Review (Weeks 13-15)

### 8.1 Explainability

**SHAP:** Applied to all ML models (income XGBoost, affordability LightGBM, risk XGBoost ensemble):
- Per-feature SHAP value stored in OpenSearch alongside every decision
- Top-3 positive and negative contributors reported in `OnboardingDecision.risk_factors`

**LIME:** Applied to document extraction:
- Token-level attribution for extracted fields
- Visualized as confidence heatmap overlay on source document in review UI

**Qwen3-32B Reviewer Copilot (via vLLM/Ollama):**

```python
prompt = f"""
You are a personal loan underwriting assistant for an Indian NBFC.
Review the following case and produce:
1. A 3-sentence plain-English summary of the applicant's profile
2. The single most important reason for the system's decision
3. Up to 3 inconsistencies or red flags, each citing the source document
4. 2 specific questions for the human reviewer to verify

Application: {application.summary()}  [Loan amount: ₹{application.amount:,.0f}, Tenure: {application.tenure}m]
Identity: {identity.summary()}
Income: {income.summary()}  [FOIR: {affordability.foir:.0%}, Verified income: ₹{income.verified_monthly_income:,.0f}/month]
CIBIL: Score {bureau.score}, Active loans: {bureau.active_loans}
Decision: {decision.summary()}
"""
```

### 8.2 Human Review UI

**Stack:** FastAPI + Jinja2 templates (no separate frontend build step required)

**Views:**

1. **Queue** — applications sorted by risk_score descending; columns: applicant name, loan amount, decision, FOIR, CIBIL score, primary reason code, age in queue
2. **Review Detail:**
   - Left pane: document viewer (PDF/image, page navigation, field bounding-box highlights)
   - Right pane: extracted fields with confidence, source document link, API-verified indicator
3. **Decision Panel:** system recommendation + override with mandatory reason code + free-text notes + submit
4. **Audit View:** full evidence chain per figure, SHAP bar chart, Qwen3 copilot narrative

### 8.3 Override Feedback Loop

All reviewer overrides feed back into model retraining data. Override reason code + reviewer notes stored alongside original feature vectors for quarterly retraining trigger.

---

## 9. Phase 4: Enterprise Hardening + RBI Compliance (Weeks 16-18)

### 9.1 MLOps

- MLflow: model registry, experiment tracking, staging → production promotion with holdout validation gate
- Feast: feature views per domain (identity, income, affordability, fraud, risk); online store (Redis), offline store (PostgreSQL)
- Evidently AI: data drift, model drift, target drift alerts; retraining triggered on drift threshold breach
- Retraining cadence: weekly scheduled + on-demand via drift alert; reviewer override feedback included

### 9.2 DPDP Act 2023 Compliance

| Requirement | Implementation |
|---|---|
| Explicit consent before processing | `consent_records` table: application_id, purpose, consent_version, consented_at, document_hash |
| Purpose limitation | Each API call (UIDAI, NSDL, CIBIL) checks `consent_records` for matching purpose before execution |
| Data deletion right | `DELETE /applications/{id}/personal-data` API: PII fields zeroed, documents deleted from MinIO; audit tombstone retained |
| Data principal access | `GET /applications/{id}/data-summary` returns all personal data held for that application |
| Consent withdrawal | Withdrawal recorded; further processing blocked; data deletion triggered |

### 9.3 PII Protection

- Microsoft Presidio: auto-detection of PAN, Aadhaar, phone, email, name, address in all stored fields
- PostgreSQL column-level encryption for PII fields (pgcrypto)
- Log masking: Aadhaar → `**** **** 1234`, PAN → `ABCDE***F`
- Audit logs: PII masked before writing to OpenSearch

### 9.4 AML / PMLA Compliance

- PEP (Politically Exposed Person) screening: checked against government-published PEP list on application receipt
- High-value loan flag: loans > ₹50L trigger enhanced due diligence workflow (additional documentation, senior reviewer mandatory)
- Suspicious transaction reporting: automated SAR (Suspicious Activity Report) queue for flagged fraud cases

### 9.5 RBI Digital Lending Guidelines 2022

| Requirement | Implementation |
|---|---|
| KFS disclosure | Key Fact Statement (APR, processing fee, tenure, EMI) generated at application acceptance and stored with consent |
| NACH mandate | EMI debit only via NACH/e-NACH mandate; mandate reference stored in application record |
| Disbursement | Loan amount disbursed only to borrower's verified bank account (account number cross-checked against bank statement) |
| LSP disclosure | Lending Service Provider name and role disclosed in KFS |
| Cooling-off period | 3-day cancellation window enforced; cancellation API implemented |

### 9.6 Operations

- RBAC roles: `admin`, `reviewer`, `senior_reviewer`, `manager`, `api_consumer`, `compliance_officer`
- Rate limiting: Redis + slowapi (100 req/min per API key, 10 req/min per upload endpoint)
- Load target: `POST /onboard` → p95 < 8s (includes OCR + extraction + identity API + CIBIL pull)
- Health checks: `/health`, `/health/ready` (all dependencies), `/health/live`
- Security: `pip-audit` + `bandit` + `safety` in CI; OWASP Top 10 review before Phase 4 complete
- Data residency enforcement: all MinIO, PostgreSQL, OpenSearch, Neo4j instances tagged `region=ap-south-1`; CI check fails if cross-region endpoint detected

---

## 10. DoD Validation Checklist (Phase 1 Test Suite)

After Phase 1 (Week 8), all tests must pass:

**Identity:**
- [ ] `test_clean_salaried_application_approves` — matching PAN/Aadhaar/application + CIBIL 750 + FOIR 0.40 → APPROVE
- [ ] `test_pan_nsdl_inactive_rejects` — NSDL returns inactive PAN → REJECT `pan_inactive_or_invalid`
- [ ] `test_aadhaar_otp_failure_rejects` — UIDAI OTP fails → REJECT `aadhaar_verification_failed`
- [ ] `test_name_mismatch_pan_aadhaar_rejects` — BGE-M3 similarity < 0.85 → REJECT `identity_mismatch_name`
- [ ] `test_dob_mismatch_rejects` — DOB differs between PAN and Aadhaar → REJECT `identity_mismatch_dob`
- [ ] `test_forged_document_metadata_flags` — PDF created_by = Photoshop → tamper flag raised

**Income:**
- [ ] `test_salary_slip_vs_bank_mismatch_flags` — salary slip ₹80K, bank credits ₹48K → `salary_slip_vs_bank_mismatch` flag raised
- [ ] `test_income_inflation_reviews` — inflated salary slip → REVIEW with `income_inflation` flag
- [ ] `test_no_salary_credits_in_bank_rejects` — no recurring salary credits found → REJECT `bank_credit_not_found`
- [ ] `test_employer_name_mismatch_flags` — slip employer ≠ application employer → `employer_name_mismatch` flag

**Affordability:**
- [ ] `test_foir_above_60_rejects` — DTI/FOIR > 0.60 → REJECT `foir_exceeded`
- [ ] `test_foir_50_to_60_reviews` — FOIR 0.55 → REVIEW `foir_marginal`

**Credit Bureau:**
- [ ] `test_cibil_below_650_rejects` — score 620 → REJECT `cibil_score_below_minimum`
- [ ] `test_dpd_90_plus_rejects` — DPD ≥ 90 in last 24m → REJECT `dpd_90_plus_in_24_months`
- [ ] `test_cibil_marginal_reviews` — score 685 → REVIEW `cibil_marginal`

**Traceability:**
- [ ] `test_every_output_field_has_evidence_chain` — all `OnboardingDecision` fields have populated `EvidenceChain`
- [ ] `test_source_chains_trace_to_minio_documents` — each chain's `SourceLocation.document_id` resolves to a real MinIO object
- [ ] `test_api_verified_fields_use_api_authoritative_method` — UIDAI/NSDL fields have `reconciliation_method = "api_authoritative"`
- [ ] `test_consent_required_before_bureau_pull` — CIBIL pull without consent record → 403 Forbidden

**Annotation Pipeline (Phase 0 gate before Phase 1a model training):**
- [ ] `test_annotation_bboxes_cover_all_gt_fields` — for each generator output, every ground-truth field has ≥ 1 annotated token with correct BIO label
- [ ] `test_layoutlmv3_finetune_f1_gte_0_90` — held-out Indian doc set F1 ≥ 0.90
- [ ] `test_qwen_anls_gte_0_75` — DocVQA held-out ANLS ≥ 0.75 before extraction deployment

---

## 11. Directory Structure

```
loip/
├── docker-compose.yml
├── .env.example
├── pyproject.toml
├── schemas/
│   ├── evidence.py              # Traceability contract (SourceLocation, ExtractedField, EvidenceChain)
│   ├── identity.py
│   ├── income.py
│   ├── affordability.py
│   ├── fraud.py
│   ├── decision.py
│   ├── consent.py               # DPDP Act consent records
│   └── bureau.py                # Credit bureau result schema
├── scripts/
│   ├── generators/
│   │   ├── generate_pan_card.py
│   │   ├── generate_aadhaar.py
│   │   ├── generate_salary_slip.py
│   │   ├── generate_bank_statement.py
│   │   ├── generate_form16.py
│   │   ├── generate_itr.py
│   │   ├── generate_gst_return.py
│   │   └── generate_offer_letter.py
│   ├── annotate/
│   │   ├── generate_annotations.py     # Generator JSON → LayoutLMv3 BIO + Donut GT
│   │   ├── label_schema.py             # BIO label definitions per document type
│   │   └── validate_annotations.py     # Assert all GT fields have ≥1 annotated token
│   ├── download_datasets.py            # MIDV-500/2020, RVL-CDIP, FUNSD, DocVQA + checksum verify
│   ├── evaluate_qwen_docvqa.py         # ANLS gate: assert ≥ 0.75 before deploying extraction
│   ├── generate_case.py                # Compose multi-doc test case
│   └── seed_db.py
├── domains/
│   ├── evidence/                # Domain 1: EvidenceChain storage and retrieval
│   ├── document_intel/          # Domain 2: Classification + OCR + extraction
│   ├── identity_trust/          # Domain 3: Entity matching + NSDL/UIDAI verification
│   ├── truth_reconciliation/    # Domain 4: Cross-document conflict resolution
│   ├── income_intel/            # Domain 5: Salary + bank + Form16/ITR reconciliation
│   ├── affordability/           # Domain 6: FOIR, DTI, disposable income
│   ├── fraud/                   # Domain 7: Forgery rules + graph fraud + behavioral anomaly
│   ├── risk_decisioning/        # Domain 8: Hard gates + CIBIL + ensemble
│   ├── explainability/          # Domain 9: SHAP + LIME + Qwen3 copilot
│   ├── human_review/            # Domain 10: Review queue + override workflow
│   ├── mlops/                   # Domain 11: MLflow + Feast + Evidently + retraining
│   └── compliance/              # Domain 12: DPDP consent, PMLA, RBI DLG, data residency
├── integrations/
│   ├── nsdl_client.py           # PAN verification API
│   ├── uidai_client.py          # Aadhaar OTP eKYC
│   ├── cibil_client.py          # CIBIL TransUnion credit report
│   ├── experian_client.py       # Experian India (fallback bureau)
│   ├── digilocker_client.py     # DigiLocker document fetch
│   └── mca21_client.py          # MCA21 employer CIN verification (Phase 2)
├── models/
│   ├── paddleocr_wrapper.py
│   ├── surya_wrapper.py
│   ├── layoutlmv3_wrapper.py
│   ├── qwen2_5_vl_wrapper.py
│   ├── donut_wrapper.py
│   ├── bge_m3_wrapper.py
│   ├── arcface_wrapper.py       # Phase 2
│   ├── minifasnet_wrapper.py    # Phase 2
│   ├── graphsage_wrapper.py     # Phase 2
│   ├── xgboost_wrapper.py
│   └── lightgbm_wrapper.py
├── pipelines/
│   ├── onboarding.py            # POST /onboard orchestrator
│   └── base.py
├── web/
│   ├── api.py
│   ├── auth.py                  # RBAC/ABAC
│   └── routes/
│       ├── onboard.py
│       ├── review.py
│       ├── evidence.py
│       ├── audit.py
│       ├── consent.py           # DPDP: data access + deletion endpoints
│       └── admin.py
├── tests/
│   ├── generators/
│   ├── annotate/
│   │   ├── test_bbox_coverage.py
│   │   └── test_annotation_format.py
│   ├── pipeline/
│   │   ├── test_onboarding.py
│   │   ├── test_identity.py
│   │   ├── test_income.py
│   │   ├── test_affordability.py
│   │   ├── test_bureau.py
│   │   └── test_decision.py
│   ├── compliance/
│   │   ├── test_consent_enforcement.py
│   │   └── test_data_residency.py
│   └── fixtures/
│       ├── clean_salaried/
│       ├── clean_self_employed/
│       ├── income_mismatch_salary_vs_bank/
│       ├── identity_mismatch_pan_aadhaar/
│       ├── income_inflated/
│       ├── cibil_below_minimum/
│       ├── foir_exceeded/
│       └── forged_document_metadata/
└── docs/
    ├── SETUP.md
    ├── API.md
    ├── RUNBOOK.md
    ├── COMPLIANCE.md            # RBI, DPDP, PMLA obligations and implementation notes
    └── DATA_GUIDANCE_NOTES.md   # Explicit notes on MIDV/RVL-CDIP domain mismatch + annotation pipeline rationale
```

---

## 12. Dependency Graph

```
Phase 0: Foundation + Data Assets + Generators + Annotation Pipeline (Weeks 1-2)
    │
    ▼  ── [Gate: annotation pipeline F1 ≥ 0.90 + Qwen ANLS ≥ 0.75]
    │
Phase 1: Core DoD Pipeline — Salaried Segment (Weeks 3-8)
    ├── 1a: Document Intel (PAN, Aadhaar, Salary Slip, Bank Statement)
    ├── 1b: Identity Trust (NSDL + UIDAI + BGE-M3 entity matching)
    ├── 1c: Income Intelligence (salary slip + bank statement, salaried only)
    ├── 1d: Affordability (FOIR primary, DTI secondary)
    └── 1e: Risk Decisioning (KYC gates → CIBIL gate → FOIR gate → ensemble)
    │
    ▼  ── [Gate: DoD test suite passes (all 21 tests green)]
    │
Phase 2: Expand Depth (Weeks 9-12)
    ├── Self-employed income module (ITR-4, GST, 12-month bank)
    ├── Additional doc types (Passport, DL, Form 16, ITR, GST returns)
    ├── Full identity (ArcFace face verify, MiniFASNet liveness, V-CIP video KYC)
    └── Fraud intelligence (graph fraud, forgery rules, behavioral anomaly)
    │
    ▼
Phase 3: Explainability + Human Review (Weeks 13-15)
    │
    ▼
Phase 4: Enterprise Hardening + RBI / DPDP Compliance (Weeks 16-18)
```

**Key milestone:** After Phase 1 (Week 8) you have a working system that satisfies the full Definition of Done for the **salaried personal loan segment** in India — cross-verified identity with UIDAI/NSDL confirmation, reconstructed income with FOIR, CIBIL-gated risk score, approve/review/reject, every figure traced to source. Phases 2-4 add self-employed coverage, face/liveness, fraud depth, explainability, and regulatory hardening.

---

## 13. Key Design Decisions

1. **Annotation pipeline as Phase 0 first-class deliverable** — the v2 plan left an unbridged gap between generator metadata and model training format. The annotation pipeline (`generate_annotations.py`) is the critical structural fix: it uses PaddleOCR bounding boxes + fuzzy field matching to produce BIO-labelled training data at 10,500+ samples before any model training begins.

2. **MIDV-500/2020 role is OCR robustness only** — these datasets contain European/Russian identity documents and cannot train Indian KYC classifiers. They test the preprocessing pipeline (deskew, deblur, threshold) against diverse capture conditions. Indian document training data comes exclusively from the generators.

3. **RVL-CDIP + FUNSD are backbone pre-training, not Indian classifiers** — domain-adapted via annotation pipeline fine-tuning. Without this distinction in the code, engineers would skip generating annotated training data, assuming the public datasets cover the domain.

4. **DocVQA gate is hard-coded in CI** — `evaluate_qwen_docvqa.py` asserts ANLS ≥ 0.75; Phase 1a cannot deploy extraction until this passes. Previously this was aspirational; now it blocks deployment.

5. **API-authoritative sources win over document extraction** — UIDAI, NSDL, and CIBIL responses use `reconciliation_method = "api_authoritative"` and override conflicting document values. This is the correct order of trust for Indian KYC.

6. **FOIR as primary affordability metric** — DTI is kept for completeness, but FOIR (which includes proposed EMI in obligations) is the metric Indian banks and RBI guidance calibrate thresholds against. Using DTI alone would produce miscalibrated thresholds.

7. **Regulatory compliance is domain 12, not a Phase 4 afterthought** — consent schema defined in Phase 0 (DPDP), API calls gated on consent from Phase 1, data residency enforced from Phase 0 infrastructure. Retrofitting compliance at the end is a regulatory risk in India's current environment.

8. **Rules before models** — Hard gates (KYC invalid, CIBIL < 650, FOIR > 0.60) execute before any ML inference. This ensures decisions remain auditable and defensible to regulators regardless of model behaviour.
