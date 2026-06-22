# LOIP demo — real-document scenario results

Real-mode demo (`LOIP_DEMO_REAL_MODELS=1`) exercised against
`/Users/developer/Downloads/Projects/RealDocs/`. Server reachable at
`http://127.0.0.1:8000/apply`. Re-run with
`bash run_tests.sh` (resets the fraud graph between scenarios so velocity
from one scenario doesn't bleed into the next).

## Summary

6 / 8 scenarios behaved exactly as planned. The 2 misses are not bugs in
the new demo override — they confirm the override gate sits on *extracted*
document fields, not on whatever the applicant typed into the form (see
"Finding" below).

| # | Inputs | Expected | Actual | Result |
|---|---|---|---|---|
| **A** | Asish full set, consistent form | Human Approval Required | **Human Approval Required** | PASS |
| **B1** | Asish PAN + Aadhaar + payslip (no bank) | Under Review | **Under Review** (`documents_missing:bank_statement`) | PASS |
| **B2** | Asish PAN + Aadhaar + bank (no payslip) | Under Review | **Under Review** (`documents_missing:salary_slip`) | PASS |
| **C1** | Asish PAN + Vijay Aadhaar + Asish income docs | Application Rejected | **Application Rejected** (`name_pan_aadhaar_mismatch`) | PASS |
| **C2** | Asish docs, typed PAN = `ABCDE12345` (malformed) | Application Rejected | Human Approval Required | FAIL¹ |
| **C3** | Asish docs, typed Aadhaar = `123412341234` (Verhoeff fail) | Application Rejected | Human Approval Required | FAIL¹ |
| **D1** | Asish docs, typed PAN ≠ document PAN | Human Approval Required | **Human Approval Required** | PASS |
| **D2** | Asish docs, declared income ₹999,999 (vs ₹82,232) | Human Approval Required | **Human Approval Required** | PASS |

¹ See "Finding — C2/C3" below.

## Finding — C2/C3

The plan hypothesised that typing a malformed PAN or a Verhoeff-invalid
Aadhaar would raise `PAN_FORMAT_INVALID` / `AADHAAR_FORMAT_INVALID` tamper
flags and reject the application. It does not — and the code is correct:

- The format/checksum check in
  [identity_trust/processor.py:41-60](../../loip/domains/identity_trust/processor.py:41)
  runs on `extracted_fields["pan_number"]` and `extracted_fields["aadhaar_number"]`,
  i.e. **what the OCR/VL model read from the uploaded document image**.
- The typed form value never reaches that check. It only feeds the
  form-vs-document cross-check in
  [web/routes/demo.py:251-310](../../loip/web/routes/demo.py:251), which
  produces human-readable mismatch strings (see C2/C3 responses) but no
  tamper flag.

So if the applicant uploads a real, valid PAN/Aadhaar, the document itself
is well-formed — typing rubbish in the form alone is not enough to trip
the tamper gate. The honest takeaway: to force `Application Rejected`
through PAN_FORMAT_INVALID / AADHAAR_FORMAT_INVALID you'd need to upload
a document image whose extracted value fails the regex / Verhoeff check,
which real-world genuine documents won't do. **C1 (mixed identity) remains
the only reject-path reachable from real, unmodified documents** in this
test set.

C2/C3 responses do contain the cross-check mismatch:

```json
"mismatches": ["PAN on document (CGYPC9928B) does not match the PAN you entered (ABCDE12345)."]
"mismatches": ["Aadhaar number on document (304288971384) does not match the number you entered (123412341234)."]
```

If we want the demo override to also reject on these form-level mismatches,
the change would be in
[web/routes/demo.py:651-685](../../loip/web/routes/demo.py:651) — extend
the reject branch to fire when `len(mismatches) > 0`. Not in scope for
this run.

## Coverage of the override branches

- `decision_label == "Human Approval Required"` — A, D1, D2 ✓
- `decision_label == "Under Review"` — B1, B2 ✓
- `decision_label == "Application Rejected"` — C1 ✓

All three branches of the override are covered by at least one real-document
scenario.

## Artifacts per scenario

Each subfolder contains:

- `request.txt` — the curl form fields and document files submitted
- `response.json` — the `/apply/submit` JSON response (decision, fraud_score, tamper_flags, mismatches, extracted_fields)
- `log_excerpt.txt` — `/tmp/loip_demo.log` lines grep'd by application_id

Folders:

- [A_human_approval/](A_human_approval/)
- [B1_missing_bank/](B1_missing_bank/)
- [B2_missing_payslip/](B2_missing_payslip/)
- [C1_mixed_identity/](C1_mixed_identity/)
- [C2_pan_format_invalid/](C2_pan_format_invalid/)
- [C3_aadhaar_checksum_invalid/](C3_aadhaar_checksum_invalid/)
- [D1_typed_pan_mismatch/](D1_typed_pan_mismatch/)
- [D2_income_overstated/](D2_income_overstated/)

## Notes & caveats

- **Doc-intel caching.** The submissions completed in ~7 s end-to-end
  (well under the 30–60 s a cold real-mode VL run takes) because the
  `DocumentIntelligenceProcessor` cache is hot from earlier in this
  session — every image hash had been seen before. The extracted fields
  are still genuine; this just means we exercised the override branch
  logic, not the underlying VL extraction throughput.
- **Fraud graph reset.** `run_tests.sh` calls `POST /apply/_reset_fraud_graph`
  before every scenario. Without that, by the 4th submission of the same
  PAN/Aadhaar pair `fraud_score` climbs above 0.60 and every subsequent
  scenario rejects regardless of inputs.
- **External APIs.** CIBIL/UIDAI/NSDL stay mocked
  (see [project-loip-known-mocks](../../../../.claude/projects/-Users-developer-Downloads-Projects/memory/project-loip-known-mocks.md)),
  so Aadhaar OTP / PAN-name verification status is not part of the demo
  override's decision input.
