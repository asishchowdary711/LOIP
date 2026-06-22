#!/usr/bin/env bash
# Demo scenario driver. Posts multipart/form-data submissions to
# /apply/submit, captures each JSON response + the matching server-log
# excerpt, then writes a PASS/FAIL summary in README.md.

set -u

BASE="http://127.0.0.1:8000"
ROOT="$(cd "$(dirname "$0")" && pwd)"
DOCS="/Users/developer/Downloads/Projects/RealDocs"
LOG="/tmp/loip_demo.log"

# Asish identity values (verified against prior real-mode submissions in
# loip/data/demo_applications/*.json).
ASISH_NAME="Vattikuti Asish Chowdary"
ASISH_MOBILE="7382890473"
ASISH_PAN="CGYPC9928B"
ASISH_AADHAAR="304288971384"
ASISH_INCOME="82232"
ASISH_LOAN="320000"

submit() {
  # submit <scenario_dir> <form_args...> -- <files...>
  local dir="$1"; shift
  mkdir -p "$dir"
  local form=() files=() saw_sep=0
  for a in "$@"; do
    if [ "$a" = "--" ]; then saw_sep=1; continue; fi
    if [ $saw_sep -eq 0 ]; then form+=("$a"); else files+=("$a"); fi
  done

  {
    echo "POST $BASE/apply/submit"
    for f in "${form[@]}"; do echo "  -F $f"; done
    for f in "${files[@]}"; do echo "  -F documents=@$f"; done
  } > "$dir/request.txt"

  local args=()
  for f in "${form[@]}"; do args+=(-F "$f"); done
  for f in "${files[@]}"; do args+=(-F "documents=@$f"); done

  # Reset the in-memory GraphSAGE fraud graph before every submission so
  # velocity from earlier scenarios in this run doesn't artificially inflate
  # fraud_score and trip the demo's >0.60 reject gate for unrelated scenarios.
  curl -s -X POST "$BASE/apply/_reset_fraud_graph" > /dev/null

  echo "[`date +%H:%M:%S`] $(basename "$dir") submitting…"
  curl -s -X POST "$BASE/apply/submit" "${args[@]}" -o "$dir/response.json"

  # Application id (best-effort) → log excerpt
  local app_id
  app_id=$(python3 -c "import json,sys; print(json.load(open('$dir/response.json')).get('application_id',''))" 2>/dev/null)
  if [ -n "$app_id" ]; then
    grep "$app_id" "$LOG" 2>/dev/null | tail -200 > "$dir/log_excerpt.txt" || true
  else
    echo "(no application_id in response; check response.json)" > "$dir/log_excerpt.txt"
  fi
  sleep 7
}

# ---------------- Scenario A — Human Approval Required ----------------
submit "$ROOT/A_human_approval" \
  "full_name=$ASISH_NAME" "mobile_number=$ASISH_MOBILE" \
  "pan_number=$ASISH_PAN" "aadhaar_number=$ASISH_AADHAAR" \
  "employment_type=salaried" "monthly_income=$ASISH_INCOME" \
  "loan_amount=$ASISH_LOAN" \
  -- \
  "$DOCS/My pan-card.jpeg" "$DOCS/My aadhaar 1.tiff" \
  "$DOCS/asish_payslip_May2026.pdf" "$DOCS/asish_bank_statement_Mar-May2026.pdf"

# ---------------- Scenario B1 — Under Review (no bank statement) ------
submit "$ROOT/B1_missing_bank" \
  "full_name=$ASISH_NAME" "mobile_number=$ASISH_MOBILE" \
  "pan_number=$ASISH_PAN" "aadhaar_number=$ASISH_AADHAAR" \
  "employment_type=salaried" "monthly_income=$ASISH_INCOME" \
  "loan_amount=$ASISH_LOAN" \
  -- \
  "$DOCS/My pan-card.jpeg" "$DOCS/My aadhaar 1.tiff" \
  "$DOCS/asish_payslip_May2026.pdf"

# ---------------- Scenario B2 — Under Review (no payslip) -------------
submit "$ROOT/B2_missing_payslip" \
  "full_name=$ASISH_NAME" "mobile_number=$ASISH_MOBILE" \
  "pan_number=$ASISH_PAN" "aadhaar_number=$ASISH_AADHAAR" \
  "employment_type=salaried" "monthly_income=$ASISH_INCOME" \
  "loan_amount=$ASISH_LOAN" \
  -- \
  "$DOCS/My pan-card.jpeg" "$DOCS/My aadhaar 1.tiff" \
  "$DOCS/asish_bank_statement_Mar-May2026.pdf"

# ---------------- Scenario C1 — Mixed identity (Asish PAN + Vijay Aadhaar)
submit "$ROOT/C1_mixed_identity" \
  "full_name=$ASISH_NAME" "mobile_number=$ASISH_MOBILE" \
  "pan_number=$ASISH_PAN" "aadhaar_number=$ASISH_AADHAAR" \
  "employment_type=salaried" "monthly_income=$ASISH_INCOME" \
  "loan_amount=$ASISH_LOAN" \
  -- \
  "$DOCS/My pan-card.jpeg" "$DOCS/RealData Aadhaar Card.jpeg" \
  "$DOCS/asish_payslip_May2026.pdf" "$DOCS/asish_bank_statement_Mar-May2026.pdf"

# ---------------- Scenario C2 — Typed PAN malformed -------------------
# Note: PAN_FORMAT_INVALID is gated on the EXTRACTED PAN. Typed-only invalid
# PAN trips the form-vs-doc mismatch path instead of a tamper flag. Captured
# for documentation.
submit "$ROOT/C2_pan_format_invalid" \
  "full_name=$ASISH_NAME" "mobile_number=$ASISH_MOBILE" \
  "pan_number=ABCDE12345" "aadhaar_number=$ASISH_AADHAAR" \
  "employment_type=salaried" "monthly_income=$ASISH_INCOME" \
  "loan_amount=$ASISH_LOAN" \
  -- \
  "$DOCS/My pan-card.jpeg" "$DOCS/My aadhaar 1.tiff" \
  "$DOCS/asish_payslip_May2026.pdf" "$DOCS/asish_bank_statement_Mar-May2026.pdf"

# ---------------- Scenario C3 — Typed Aadhaar checksum invalid --------
# Note: AADHAAR_FORMAT_INVALID is gated on the EXTRACTED Aadhaar. Same
# caveat as C2.
submit "$ROOT/C3_aadhaar_checksum_invalid" \
  "full_name=$ASISH_NAME" "mobile_number=$ASISH_MOBILE" \
  "pan_number=$ASISH_PAN" "aadhaar_number=123412341234" \
  "employment_type=salaried" "monthly_income=$ASISH_INCOME" \
  "loan_amount=$ASISH_LOAN" \
  -- \
  "$DOCS/My pan-card.jpeg" "$DOCS/My aadhaar 1.tiff" \
  "$DOCS/asish_payslip_May2026.pdf" "$DOCS/asish_bank_statement_Mar-May2026.pdf"

# ---------------- Scenario D1 — Typed PAN does not match document ----
submit "$ROOT/D1_typed_pan_mismatch" \
  "full_name=$ASISH_NAME" "mobile_number=$ASISH_MOBILE" \
  "pan_number=ABCDE1234F" "aadhaar_number=$ASISH_AADHAAR" \
  "employment_type=salaried" "monthly_income=$ASISH_INCOME" \
  "loan_amount=$ASISH_LOAN" \
  -- \
  "$DOCS/My pan-card.jpeg" "$DOCS/My aadhaar 1.tiff" \
  "$DOCS/asish_payslip_May2026.pdf" "$DOCS/asish_bank_statement_Mar-May2026.pdf"

# ---------------- Scenario D2 — Income overstated ---------------------
submit "$ROOT/D2_income_overstated" \
  "full_name=$ASISH_NAME" "mobile_number=$ASISH_MOBILE" \
  "pan_number=$ASISH_PAN" "aadhaar_number=$ASISH_AADHAAR" \
  "employment_type=salaried" "monthly_income=999999" \
  "loan_amount=$ASISH_LOAN" \
  -- \
  "$DOCS/My pan-card.jpeg" "$DOCS/My aadhaar 1.tiff" \
  "$DOCS/asish_payslip_May2026.pdf" "$DOCS/asish_bank_statement_Mar-May2026.pdf"

# ---------------- Summary ----------------
python3 - "$ROOT" <<'PY'
import json, os, sys, glob
root = sys.argv[1]

PLAN = [
    # (dir, expected_label, expected_decision, extra_check, note)
    ("A_human_approval",          "Human Approval Required", "review", None, "Happy path"),
    ("B1_missing_bank",           "Under Review",            "review", "bank_statement", "Missing bank statement"),
    ("B2_missing_payslip",        "Under Review",            "review", "salary_slip",   "Missing payslip"),
    ("C1_mixed_identity",         "Application Rejected",    "reject", "name_pan_aadhaar_mismatch", "PAN + foreign Aadhaar"),
    ("C2_pan_format_invalid",     "Application Rejected",    "reject", "pan_format_invalid", "PLAN: may not trip — tamper gate is on extracted PAN"),
    ("C3_aadhaar_checksum_invalid","Application Rejected",   "reject", "aadhaar_format_invalid", "PLAN: may not trip — tamper gate is on extracted Aadhaar"),
    ("D1_typed_pan_mismatch",     "Human Approval Required", "review", None, "Form mismatch — no tamper"),
    ("D2_income_overstated",      "Human Approval Required", "review", None, "Income mismatch — no tamper"),
]

rows = []
for d, exp_label, exp_dec, extra, note in PLAN:
    p = os.path.join(root, d, "response.json")
    if not os.path.exists(p):
        rows.append((d, exp_label, "—", "—", "—", "MISSING", note))
        continue
    try:
        r = json.load(open(p))
    except Exception as e:
        rows.append((d, exp_label, f"ERR: {e}", "—", "—", "FAIL", note))
        continue
    label = r.get("decision_label") or "—"
    dec   = r.get("decision") or "—"
    tamper = r.get("identity_tamper_flags") or []
    rflags = r.get("review_flags") or []
    extras = ", ".join(tamper) if tamper else (", ".join(f for f in rflags if "documents_missing" in f) or "")
    ok = (label == exp_label) and (dec == exp_dec)
    if extra:
        if extra.startswith("documents_missing") or extra in {"bank_statement","salary_slip"}:
            ok = ok and any(extra in f for f in rflags)
        else:
            ok = ok and (extra in [str(t).lower() for t in tamper])
    rows.append((d, exp_label, label, dec, extras, "PASS" if ok else "FAIL", note))

readme = os.path.join(root, "README.md")
with open(readme, "w") as f:
    f.write("# LOIP demo — real-document scenario results\n\n")
    f.write("Generated by `run_tests.sh`. Server: real-mode (`LOIP_DEMO_REAL_MODELS=1`).\n\n")
    f.write("| Scenario | Expected label | Actual label | Decision | Tamper / missing | Result | Notes |\n")
    f.write("|---|---|---|---|---|---|---|\n")
    for r in rows:
        f.write("| " + " | ".join(str(x).replace("|","\\|") for x in r) + " |\n")
    f.write("\n## Artifacts per scenario\n\n")
    for d,*_ in [(p[0],) for p in PLAN]:
        f.write(f"- [{d}/]({d}/) — `request.txt`, `response.json`, `log_excerpt.txt`\n")

print("WROTE", readme)
for r in rows: print(r)
PY
