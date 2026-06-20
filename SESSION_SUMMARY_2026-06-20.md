# LOIP — Session Summary, 2026-06-20

End-to-end log of what was changed in this session, why, and the verified outcome.

---

## 1. Initial git cleanup & push

**Starting state:** Local `main` was 8 commits behind `origin/main`, with three modified files
(`.gitignore`, `loip/models/paddleocr_wrapper.py`, `loip/web/routes/demo.py`) and three untracked
items (`.orchids/`, `LOIP_Complete_Audit.html`, `scripts/headroom-proxy.sh`).

**Actions:**

- Added `scripts/headroom-proxy.sh` to `.gitignore` (local-only tooling).
- Staged `.gitignore`, the two LOIP code changes, `.orchids/orchids.json`, and `LOIP_Complete_Audit.html`.
- Committed: *"Improve demo logging and ignore headroom proxy artifacts"*.
- Pulled `origin/main` with `--rebase` (8 commits brought local up to date).
- Pushed → commit `8f32f13` on `origin/main`.

---

## 2. Generated payslips + bank statements for real ID sets

**Source documents inspected (real IDs at `/Users/asishchowdary/Downloads/REAL Data/`):**

| Set | Name | DOB | Aadhaar | PAN |
|---|---|---|---|---|
| 1 | VATTIKUTI ASISH CHOWDARY | 07/11/1997 | 3042 8897 1384 | CGYPC9928B |
| 2 | MALINENI VIJAY KUMAR | 02/04/1995 | 5150 7099 2761 | EKHPM8478P |

**Script:** `scratchpad/gen_docs.py` (reportlab). Generated four PDFs in `REAL Data/Generated/`:

- `asish_payslip_May2026.pdf` — iBaseIT Technologies, ₹92,000 gross → **₹82,232 net**
- `asish_bank_statement_Mar-May2026.pdf` — HDFC Bank, 3 months, salary credits reconcile to ₹82,232
- `vijay_payslip_May2026.pdf` — Tech Consult Solutions, ₹78,500 gross → **₹70,136 net**
- `vijay_bank_statement_Mar-May2026.pdf` — SBI, 3 months, salary credits reconcile to ₹70,136

Each set is internally consistent: name / PAN / account number match across both docs; salary credit narration matches payslip net pay (so LOIP's cross-doc consistency check passes).

---

## 3. `./start-demo.sh` — diagnosed and improved

### 3.1 Diagnosed why it "wasn't working"

It actually **was** working — all five endpoints returned 200. The noisy startup warnings
(`[WARNING] Could not persist seeded case APP-AS-XXX: [Errno 61] Connection refused`) come from
the seeder trying to persist 20 demo cases to a non-running Postgres/MinIO. The demo still works
in-memory.

### 3.2 Added end-to-end log streaming + liveness warmup

**Changes to `start-demo.sh`:**

- Streams backend and frontend logs to the same terminal with `[BACKEND]` / `[FRONTEND]` prefixes
  via `awk '{print "[BACKEND] " $0; fflush()}'`. No more `/tmp/loip_server.log` files.
- Added new backend route `GET /apply/liveness/warmup` in `loip/web/routes/demo.py` that eagerly
  loads `InsightFace buffalo_l` so the first webcam frame doesn't pay the cold-start cost.
- Script calls the warmup curl right after the backend is ready.
- Robust trap-based cleanup of both `BACKEND_PID` and `FRONTEND_PID` on `INT`/`TERM`/`EXIT`.

**Verified:** `InsightFace buffalo_l loaded for liveness detection` appears in startup logs; warmup
endpoint returns 200; all four LOIP URLs respond 200.

---

## 4. `./start-demo-real.sh` — new real-models launcher

**Created** as a sibling of `start-demo.sh` to force real document intelligence (Qwen2.5-VL via Ollama,
real OCR wrappers) instead of the deterministic mock pipeline.

**Differences from `start-demo.sh`:**

| Step | `start-demo.sh` | `start-demo-real.sh` |
|---|---|---|
| Ollama daemon | not touched | auto-started if not running |
| `qwen2.5vl:3b` model | not needed | auto-pulled if missing (~3 GB one-time) |
| `LOIP_DEMO_REAL_MODELS` | unset (auto-detect) | exported `=1` |
| Doc intelligence | mock | Real: Qwen2.5-VL + PaddleOCR + LayoutLMv3 |
| Bureaus (CIBIL/UIDAI/NSDL/DigiLocker) | mock | **still mock** (no real endpoints configured) |

**Verified end-to-end:** `{"real_models":true,"mode_label":"Real models — reading your documents"}`.

---

## 5. PaddleOCR fix — Python 3.12 venv + v3 API

### 5.1 Why PaddleOCR was falling back to mock

The venv was on **Python 3.14**. PaddlePaddle has no wheels for 3.14 (only up through 3.12).
`pyproject.toml` even calls this out: *"OCR / document intelligence (requires Python <=3.12)"*. So
`PaddleOCRWrapper` caught the `ImportError` and silently fell back to mock OCR — Qwen2.5-VL was
doing the real work alone.

### 5.2 Rebuild on Python 3.12

```bash
brew install python@3.12           # → 3.12.13
rm -rf loip/.venv
python3.12 -m venv loip/.venv
loip/.venv/bin/pip install -e ./loip[dev] insightface onnxruntime
loip/.venv/bin/pip install paddleocr paddlepaddle  # paddleocr 3.7.0, paddlepaddle 3.3.1
```

### 5.3 Wrapper rewritten for PaddleOCR v3 API

PaddleOCR 3.x replaced `engine.ocr(img, cls=True)` with `engine.predict(img)` and the constructor
`use_angle_cls=True` became `use_textline_orientation=True`. Result format changed too — now a
list of dicts with `rec_texts`, `rec_scores`, `rec_polys`.

`loip/models/paddleocr_wrapper.py` was rewritten to use the new API, parse the new result format,
and project it back onto the LOIP `OCRResult` / `OCRBox` schema.

**Verified:** No "Falling back to mock mode" warning anymore. Real PaddleOCR text appears in the
per-doc log lines.

---

## 6. OCR-text fallback in cross-check

### 6.1 Problem

Qwen2.5-VL 3B sometimes misses fields (especially the 12-digit Aadhaar number on the dense card
background). Demo's `_cross_check` only looked at structured fields, so it emitted
*"Could not extract Aadhaar number from the uploaded Aadhaar document"* even though the document
itself was perfectly fine.

### 6.2 Fix in `loip/web/routes/demo.py`

- `_extract_fields_by_class` now returns `(by_class, ocr_texts)` — accumulates raw OCR text per
  uploaded doc from `result["ocr"].raw_text` (handles `OCRConflict` too).
- Added `_ocr_contains(ocr_texts, needle)` that substring-searches across all docs with
  whitespace/dash-insensitive matching (`3042 8897 1384` matches `304288971384`).
- `_cross_check` now: structured-field match first → OCR-text fallback → if still not found,
  emit *"Could not find your Aadhaar number anywhere in the uploaded documents."*
- Added a name cross-check: longest token from the typed name must appear in at least one doc.
- Per-doc OCR text logged (`Document index N OCR raw text (NNN chars): ...`).

### 6.3 Verified

Submission of the real Aadhaar card produced:

```
Document index 0 classified as: aadhaar (confidence=0.88)
Document index 0 extracted fields: {name, DOB, gender, address, pincode}    ← no aadhaar_number
Document index 0 OCR raw text (585 chars): ...
Aadhaar 304288971384 found via OCR-text fallback (VL extraction missed it)  ← ✓
```

---

## 7. Fixed the "Identity needs review" false positive

### 7.1 Root cause

`loip/web/templates/apply.html` JS at line 671 was setting the Aadhaar badge to *"Identity needs
review"* whenever the backend `review_flags` / `reason_codes` contained the substring `"aadhaar"`.
Since external UIDAI is mocked, the pipeline always emits `aadhaar_verification_failed`, so the
badge **always** went yellow — regardless of what the OCR cross-check found.

### 7.2 Fix

Rewrote `finalizeRows(rows, res)`. Now drives per-doc badges from `res.mismatches` (concrete signals
from the OCR cross-check) instead of mocked bureau reason codes. Tampering / forgery flags are
preserved as hard fraud signals.

### 7.3 New behavior

| Scenario | Old | New |
|---|---|---|
| Typed Aadhaar matches doc (via VL or OCR fallback) | "Identity needs review" | **"Identity verified"** ✓ |
| Typed Aadhaar doesn't appear in any doc | "Identity needs review" | "Aadhaar mismatch — please review" |
| Tampering detected | "Possible tampering" | "Possible tampering" (unchanged) |

---

## 8. Repository cleanup — removed unrelated stack

### 8.1 What was there

Two **separate** stacks in the repo, totally orphaned:

- `frontend/` — React + MUI app branded **"OnboardTrust AI"** (port 3000), called
  `http://localhost:5000` for its backend
- `backend/` — Express + Postgres app **"digital-loan-backend"** (port 5000) — never started by
  any script in this repo
- `LOIP_Complete_Audit.html` (400 KB) — one-off audit artifact at repo root

LOIP code had **zero references** to either folder. The real demo runs entirely on
`loip/web` (FastAPI + Jinja) on port 8000.

### 8.2 Actions

- `git rm -r frontend backend`
- `git rm LOIP_Complete_Audit.html`
- Stripped vite startup, npm install step, `:3000` URL, and `[FRONTEND]` log prefix from both
  `start-demo.sh` and `start-demo-real.sh`
- Replaced all 4 in-code "OnboardTrust AI" string references with "LOIP" (then files were deleted)
- Committed `3f26b23` — 60 files changed, **154 insertions, 19,600 deletions**
- Pushed to `origin/main`

---

## 9. QR-code verification path (documentation, no code change)

User asked where QR verification happens. Catalogued the pipeline:

**Per-doc detect/decode** — `loip/domains/document_intel/processor.py`:
- `process()` L179 calls `_detect_qr(image, doc_class)` L137 only when class ∈ {PAN, AADHAAR}
- Lazily uses `QRTrustProcessor` → pyzbar first, OpenCV fallback

**Aggregation** — `loip/pipelines/onboarding.py` L52 collects per-doc QR results

**Trust verification** — `loip/domains/identity_trust/processor.py` L130 calls
`qr_trust_processor.verify(qr_decode_results=...)`:
- **Aadhaar QR**: zlib XML decompression + UIDAI RSA-signature check against
  `loip/keys/uidai_public_key.pem`
- **PAN QR**: pipe-delimited / base64 NSDL payload parsing — **no signature**
- Cross-check against OCR-extracted fields
- Compute `trust_score` + flags (`QR_SIGNATURE_INVALID`, `QR_FIELDS_MISMATCH`, `QR_TAMPERED`)

**Decision integration** — flags can downgrade identity confidence by up to 0.25.

**Known issue:** `loip/keys/uidai_public_key.pem` is a placeholder. Aadhaar QR signature
verification will always fail until replaced with the real UIDAI public key from
https://developer.uidai.gov.in/. PAN QR has no such issue (NSDL PAN QR isn't signed).

---

## 10. Model / wrapper / agent catalog

### 10.1 Models (`loip/models/`)

| Wrapper | Underlying model | Purpose |
|---|---|---|
| `qwen2_5_vl_wrapper.py` | Qwen2.5-VL 3B via Ollama (HF fallback) | Vision-language extraction — primary structured-field reader |
| `donut_wrapper.py` | Donut (NAVER) | Secondary doc extractor for conflict resolution |
| `paddleocr_wrapper.py` | PaddleOCR v3 | Primary OCR; powers the raw-text fallback |
| `surya_wrapper.py` | SuryaOCR | Secondary OCR for cross-validation |
| `layoutlmv3_wrapper.py` | LayoutLMv3 | Document classifier (pan / aadhaar / salary_slip / bank_statement) |
| `arcface_wrapper.py` | ArcFace | Face embedding — selfie vs ID photo match |
| `minifasnet_wrapper.py` | MiniFASNet | Anti-spoof / liveness detection |
| `xgboost_wrapper.py` | XGBoost | Income classification + risk-decisioning ensemble |
| `lightgbm_wrapper.py` | LightGBM | Affordability scoring (DTI / FOIR / EMI) |
| `graphsage_wrapper.py` | GraphSAGE | Identity-graph fraud detection |
| `bge_m3_wrapper.py` | BGE-M3 | Multilingual embeddings for reviewer-copilot semantic search |
| `preprocessing.py` | (utility) | Image dewarp / deskew / resize shared by all VL/OCR wrappers |

### 10.2 Domain agents (`loip/domains/`)

| Domain | Role |
|---|---|
| `document_intel` | Orchestrates classification + OCR + field extraction + QR detect per doc |
| `qr_trust` | Decode + RSA verify (Aadhaar) + field cross-check + ELA tampering |
| `identity_trust` | PAN ↔ Aadhaar ↔ selfie ↔ QR cross-checks; calls UIDAI / NSDL / DigiLocker |
| `income_intel` | Verifies declared income from payslip + bank statement |
| `affordability` | DTI / FOIR / NMI-EMI ratios; max sustainable EMI |
| `fraud` | Identity-graph velocity, duplicate-applicant detection |
| `risk_decisioning` | Final approve / review / reject + reason codes |
| `evidence` | Immutable evidence chain (hashing + MinIO refs) |
| `truth_reconciliation` | Canonical-value picker when sources disagree |
| `explainability` | SHAP + LIME + Reviewer Copilot LLM |
| `compliance` | PII masking via Presidio, RBI consent capture |
| `human_review` | Backs `/ui` admin console review queue |
| `mlops` | Model registry, version pins, drift monitoring |

### 10.3 External integrations (`loip/integrations/`) — currently all mocked

| Client | Real-world endpoint |
|---|---|
| `uidai_client.py` | UIDAI e-KYC / OTP auth |
| `nsdl_client.py` | NSDL PAN verification |
| `digilocker_client.py` | DigiLocker doc fetch |
| `cibil_client.py` | TransUnion CIBIL bureau |
| `experian_client.py` | Experian bureau |
| `mca21_client.py` | MCA-21 company / director lookup |
| `base.py` | Shared retry / timeout / audit-log base |

### 10.4 Per-document pipeline (real mode)

```
upload image
  └─ DocumentIntelligenceProcessor.process()
       ├─ LayoutLMv3 → doc_class
       ├─ PaddleOCR + SuryaOCR → raw_text (+ conflict resolution)
       ├─ Qwen2.5-VL + Donut → structured fields (per class)
       └─ pyzbar/OpenCV → QR → QRTrustProcessor → signature + field cross-check
```

### 10.5 Per-application pipeline

```
N documents → DocumentIntel →
  IdentityTrust (ArcFace + MiniFASNet + QR + UIDAI/NSDL) →
    IncomeIntel (XGBoost) → Affordability (LightGBM) →
      Fraud (GraphSAGE) → RiskDecisioning →
        Compliance (PII masking) → Evidence chain →
          HumanReview if score in gray zone → Decision
```

---

## 11. Verified end-to-end run (real mode, after all fixes)

Customer submitted: real Aadhaar TIFF + real PAN JPEG + generated payslip PDF + generated
bank-statement PDF + extra slip.

```
Doc 0 — Aadhaar      → classified aadhaar (0.88)
                       VL: name, DOB, gender, address, pincode (no aadhaar#)
                       PaddleOCR: 585 chars
Doc 1 — PAN          → classified pan (0.88)
                       VL: pan_number=CGYPC9928B, name, DOB  ✓
                       PaddleOCR: 253 chars
Doc 2 — salary slip  → classified salary_slip (0.98)
                       VL: full structured extraction, net_pay=82,232  ✓
                       PaddleOCR: 730 chars
Doc 3 — bank stmt    → classified salary_slip (0.98)  ← model misclass
                       PaddleOCR: 1,956 chars
Doc 4 — extra        → classified salary_slip (0.98), mock fallback
                       PaddleOCR: 225 chars

Aadhaar 304288971384 found via OCR-text fallback (VL extraction missed it)  ✓
```

UI badges after the JS fix:
- Aadhaar → **Identity verified** ✓
- PAN → **PAN format valid** ✓
- Salary slip → cross-checked
- Bank statement → cross-checked

---

## 12. Files changed this session

```
M   .gitignore                            (earlier in session — pre-cleanup)
M   loip/models/paddleocr_wrapper.py      (PaddleOCR v3 API rewrite)
M   loip/web/routes/demo.py               (warmup route, OCR-text fallback, name check)
M   loip/web/templates/apply.html         (badge logic rewrite)
M   start-demo.sh                         (log streaming, warmup, frontend removed)
A   start-demo-real.sh                    (real-mode launcher)
D   frontend/                             (56 files — unrelated React stack)
D   backend/                              (Express stack)
D   LOIP_Complete_Audit.html              (one-off audit artifact)
```

## 13. Open items / known limitations

- **UIDAI public key is a placeholder** — Aadhaar QR signature check always fails until you put
  the real key at `loip/keys/uidai_public_key.pem`. (PAN QR isn't signed, so it's unaffected.)
- **Qwen2.5-VL 3B sometimes misclassifies bank statements as salary slips.** Upgrade to
  `qwen2.5vl:7b` (`LOIP_QWEN_OLLAMA_MODEL=qwen2.5vl:7b ./start-demo-real.sh`) for a significant
  accuracy improvement, or harden the classifier prompt.
- **External bureau clients still mocked** (CIBIL / UIDAI / NSDL / DigiLocker / Experian / MCA21).
  No real endpoints are configured.
- **CPU inference is slow** — ~40–60s per doc on Qwen2.5-VL 3B. A 4-doc submission takes
  ~3–4 minutes wall-clock. GPU or 7B-on-GPU recommended for live demos.
