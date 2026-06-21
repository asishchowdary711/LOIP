# Replace eligibility widget with inline income-based hint

## Context

The previous change added a standalone "Check your eligibility" widget on `/apply` — its own salary input, tenure buttons, principal slider, EMI display, and CTA. The user's actual intent was simpler: *"show the eligible loan amount based on the user's income. That's it."*

Two real problems with the current state:

1. **Duplicate input on the same page.** The widget asks for salary in `<input id="eligSalary">` (`apply.html:387`) while the loan form already asks for the same value in `<input name="monthly_income">` (`apply.html:442`). Users see two income prompts on the same page. This is what the user meant by "in both the pages" — there is no second page (no React frontend exists in this repo; the entire customer surface is Jinja2).
2. **"Not working" report.** The widget JS, CSS, HTML, and `/apply/eligibility` route all line up correctly. Most likely cause is browser caching of the pre-widget `apply.html` (no cache-busting in place). The redesign below makes this moot by removing the widget entirely.

The user also asked us to leverage LightGBM/XGBoost since they're already in the project. Investigation:

- `loip/models/lightgbm_wrapper.py:36` — `LightGBMWrapper.predict()` requires `foir`, `disposable_income`, `liquidity_score`. Cannot run salary-only.
- `loip/models/xgboost_wrapper.py:47` — `XGBoostWrapper.predict()` requires 7 features including bureau score. Cannot run salary-only.
- `loip/domains/affordability/processor.py:61` — the FOIR check uses a marginal cap of `0.50`. This IS the math LightGBM affordability evaluates downstream. Using it for the eligibility hint keeps the hint mathematically aligned with the project's actual decision pipeline, even though the ML model itself only runs on the full submitted application.

## Recommended approach

### Step 1 — Delete the standalone widget from `apply.html`

Remove three blocks added by the previous implementation:

- The CSS for `.elig*`, `.tenure-btns`, `.slider-row`, `.emi-display`, `.elig-cta`, `.elig-error` (added before `</style>`, after the `@media` rule).
- The HTML block `<div class="elig" id="eligWidget">…</div>` (between the modebar and the `<!-- ============ FORM VIEW ============ -->` comment).
- The IIFE in the `<script>` block (starts with `/* ---------- eligibility widget ---------- */`, ends at the matching `})();`) — including helper functions, fetch logic, slider/tenure handlers, and the CTA pre-fill.

### Step 2 — Add a minimal inline hint hooked to the existing income field

Hook into the existing `monthly_income` input (`apply.html:326`). New behaviour, ~30 lines of JS inside a small IIFE at the start of the `<script>` block:

- On `blur` of `[name="monthly_income"]`, if the value parses to ≥ 10,000, fetch `/apply/eligibility?salary=<value>`.
- Render a small helper line directly below the `loan_amount` field (`apply.html:328`):
  > `✓ Eligible for up to ₹X,XX,XXX based on your income.  [Use this amount]`
- `[Use this amount]` sets `loan_amount` and dispatches an `input` event so the existing `refresh()` (apply.html:481) picks it up and updates the progress bar.
- If salary < 10,000 or fetch fails, hide the hint silently. Existing form validation already handles range errors.
- Style with existing CSS variables only (`--muted`, `--accent-2`) — no new component classes.

Place the hint as a sibling element appended to `amountField.parentElement` so it stays close to the loan-amount input even if the form layout changes.

### Step 3 — Replace the eligibility math with the project's FOIR formula

In `loip/services/eligibility.py`, replace the `min(salary × 24, 40_00_000)` rule with the FOIR-based math used by `AffordabilityProcessor`:

```python
FOIR_CAP = 0.50         # matches AffordabilityProcessor marginal threshold
RATE_PA  = 0.14         # matches AffordabilityProcessor default
TENURE_M = 60           # max personal-loan tenure in India — gives ceiling

max_emi = salary * FOIR_CAP
r = RATE_PA / 12
factor = (r * (1 + r) ** TENURE_M) / ((1 + r) ** TENURE_M - 1)
max_principal = int(max_emi / factor)              # round down naturally
max_principal = (max_principal // 1000) * 1000     # round to nearest ₹1,000
```

- Keep validation: salary ∈ [10_000, 10_00_00_000], raise `ValueError("Salary out of range")`.
- Simplify response shape — the UI only needs `max_principal`. Drop `multiplier`, `tenure_months`, `rate_pa` (slider/tenure UI is gone). Add a short `rationale` string for transparency:
  ```python
  return {
      "salary": salary,
      "max_principal": max_principal,
      "rationale": "FOIR ≤ 50% at 14% p.a. over 60 months (aligns with LightGBM affordability check)",
  }
  ```

Sample expected values (verify when implementing):

| Salary | max_emi | max_principal (rounded ₹1k) |
|--------|---------|------------------------------|
| 25,000 | 12,500 | ≈ ₹5,38,000 |
| 50,000 | 25,000 | ≈ ₹10,77,000 |
| 1,00,000 | 50,000 | ≈ ₹21,55,000 |
| 2,00,000 | 1,00,000 | ≈ ₹43,10,000 |

(No artificial ₹40L cap — FOIR is the only ceiling, matching the affordability model.)

### Step 4 — Update tests

- `tests/test_eligibility.py` — recompute expected `max_principal` for each test case using the formula above (do the math, write the literal expected ints — do not call the function to derive the expected value). Drop `multiplier`/`tenure_months`/`rate_pa` assertions; add a `"FOIR"` substring assertion on the new `rationale` field. Keep all 4 ValueError tests.
- `tests/test_eligibility_route.py` — update the valid-salary test for the new shape. Error-path tests stay identical.

### Step 5 — Update spec and plan docs (small note, do not rewrite)

- Append a short "Revised 2026-06-21" note at the top of `docs/superpowers/specs/2026-06-20-loan-suggestions-design.md` linking to this plan.
- Same one-line note at the top of `docs/superpowers/plans/2026-06-20-loan-eligibility-widget.md`.

## Files to modify

| File | Change |
|------|--------|
| `loip/web/templates/apply.html` | Delete ~220 lines of widget CSS/HTML/JS; add ~30 lines of income-listener + hint |
| `loip/services/eligibility.py` | Replace 24× rule with FOIR formula; new response shape |
| `tests/test_eligibility.py` | Update expected `max_principal` values, drop dropped fields, add rationale check |
| `tests/test_eligibility_route.py` | Update valid-salary response-shape assertion |
| `docs/superpowers/specs/2026-06-20-loan-suggestions-design.md` | One-line revision note at top |
| `docs/superpowers/plans/2026-06-20-loan-eligibility-widget.md` | One-line revision note at top |

## Why not call LightGBM/XGBoost directly from the eligibility endpoint?

LightGBM affordability needs FOIR + disposable income + liquidity score; XGBoost risk needs 7 features including bureau score. Neither can be called with salary alone without inventing all of their other inputs — which would make the score meaningless. The honest answer for a salary-only hint is to use the **same FOIR threshold the LightGBM model evaluates** so the hint and the downstream model are mathematically aligned. The actual ML models run on the full submitted application, where all required features are present.

## Verification

1. `loip/.venv/bin/python -m pytest tests/ -v` — expect 11 passed with the new numbers.
2. `./start-demo.sh`, then **hard-refresh** (Cmd+Shift+R) `http://localhost:8000/apply`.
3. Confirm: no standalone "Check your eligibility" block above the form.
4. Type a salary (e.g., `50000`) into the **Monthly income** field, tab out → small hint appears under the Loan amount field reading `✓ Eligible for up to ₹10,77,000 based on your income. [Use this amount]`.
5. Click `[Use this amount]` → Loan amount field fills with `1077000`, progress bar advances, footnote updates.
6. Type `5000` → hint hides silently (no error, since the form will validate on its own).
7. Type `200000` → hint shows `₹43,10,000` (no artificial ceiling).
