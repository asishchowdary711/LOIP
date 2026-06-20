# Loan Eligibility Suggestions — Design Spec

**Date:** 2026-06-20
**Feature:** Inline loan eligibility widget on `/apply`
**Scope:** Personal loans in India, salary-only input

---

## Overview

Add an inline eligibility widget to the existing `/apply` page on the React customer portal. The user enters their monthly net salary, picks a tenure, drags a principal slider, and sees a live EMI calculation. One click pre-fills the existing loan application form.

No ML. No database. Rules-based eligibility via a new FastAPI endpoint, with EMI computed client-side for instant slider feedback.

---

## Decisions Made

| Question | Decision |
|----------|----------|
| Where does this live? | Inline on `/apply`, above the existing 7-field form |
| Input fields | Salary only (no existing EMIs, no age, no city) |
| UI shape | Interactive slider (principal) + segmented tenure buttons |
| Tenure options | 12, 24, 36, 48, 60 months (segmented buttons, 36 default) |
| Interest rate | Fixed 12% p.a. for demo |
| Approach | Rules in backend (FastAPI endpoint), EMI in frontend |
| ML | None — deterministic rule. Clean upgrade path to LightGBM later |

---

## Architecture

### Backend

**New service:** `loip/services/eligibility.py`

```python
def calculate_eligibility(salary: int) -> dict:
    """
    Returns max principal, tenure options, and rate for a given monthly net salary.
    Raises ValueError if salary < 10,000 or > 10,00,00,000.
    """
    if salary < 10_000 or salary > 10_00_00_000:
        raise ValueError("Salary out of range")

    max_principal = min(salary * 24, 40_00_000)

    return {
        "salary": salary,
        "max_principal": max_principal,
        "multiplier": 24,
        "rate_pa": 0.12,
        "tenure_months": [12, 24, 36, 48, 60],
    }
```

**New route:** `loip/web/routes/eligibility.py`

- `GET /apply/eligibility?salary=<int>`
- Returns the dict above as JSON (200)
- Returns 422 for invalid/out-of-range salary

**Registration:** Mount on the existing FastAPI app alongside the other `/apply` routes.

### Frontend

**New component:** `loip/frontend/src/components/LoanEligibilityWidget.jsx`

Placed above the existing 7-field form on `/apply`, collapsible.

**Behaviour:**

1. Salary input with placeholder "Enter monthly net salary (₹)"
2. On blur/enter → `GET /apply/eligibility?salary=...`
3. On response, widget expands showing:
   - Headline: "You're eligible for up to ₹X"
   - Segmented tenure buttons: `12 | 24 | [36] | 48 | 60`
   - Principal slider: ₹50,000 → max_principal, step ₹10,000
   - Default slider position: roughly 60% of max
   - Live EMI: updates on every slider drag + tenure tap (client-side math)
   - Total interest: shown subtly below EMI
   - CTA: "Apply for ₹X over Y months →"
4. CTA click → widget collapses, form scrolls into view with amount + tenure pre-filled

**EMI formula (client-side, reducing balance):**

```
r = rate_pa / 12
EMI = P × r × (1+r)^n / ((1+r)^n − 1)
total_interest = (EMI × n) − P
```

---

## Data Flow

```
User types salary
      │
      ▼
GET /apply/eligibility?salary=35000
      │
      ▼
Backend: min(35000 × 24, 40L) = 8,40,000
      │
      ▼
Response: { max_principal: 840000, rate_pa: 0.12, tenure_months: [...] }
      │
      ▼
Frontend: expand widget, render slider + buttons
      │
      ▼
User drags slider / taps tenure → EMI recalc (client-side, no network)
      │
      ▼
User clicks CTA → pre-fill form fields, scroll down
```

---

## Edge Cases

| Scenario | Behaviour |
|----------|-----------|
| Salary < ₹10,000 | Inline message: "Minimum salary ₹10,000 for personal loan eligibility" |
| Salary > ₹10Cr | 422 from backend → "Please enter a valid salary" |
| Non-numeric input | 422 from backend → "Please enter a valid salary" |
| Network error | Widget stays collapsed; user can fill form manually |
| Empty salary | Widget stays collapsed, no fetch |

---

## Sample Outputs

| Salary | Max Principal | Tenure | EMI | Total Interest |
|--------|--------------|--------|-----|----------------|
| ₹25,000 | ₹6,00,000 | 36 mo | ₹19,929 | ₹1,17,444 |
| ₹35,000 | ₹8,40,000 | 36 mo | ₹27,901 | ₹1,64,436 |
| ₹50,000 | ₹12,00,000 | 48 mo | ₹31,614 | ₹3,17,472 |
| ₹1,00,000 | ₹24,00,000 | 60 mo | ₹53,376 | ₹8,02,560 |
| ₹2,00,000 | ₹40,00,000 (cap) | 60 mo | ₹88,960 | ₹13,37,600 |

---

## File Layout

### New files
- `loip/services/eligibility.py` — eligibility rule function
- `loip/web/routes/eligibility.py` — FastAPI route
- `loip/frontend/src/components/LoanEligibilityWidget.jsx` — widget component
- `tests/test_eligibility.py` — unit tests for the rule
- `tests/test_eligibility_route.py` — API route tests

### Modified files
- App router (to register the new route)
- `/apply` page component (to mount the widget and handle pre-fill callback)

---

## Testing

### Unit tests (`tests/test_eligibility.py`)
- ₹25k salary → ₹6L max principal
- ₹2L salary → ₹40L cap (hit ceiling)
- Below ₹10k → ValueError
- Negative / zero → ValueError

### Route tests (`tests/test_eligibility_route.py`)
- 200 with valid salary, verify response shape and values
- 422 with salary below minimum
- 422 with non-numeric input

### Frontend
- Visual verification only (demo-grade, no E2E tests)

---

## Future Upgrade Path

When more inputs are added (existing EMIs, age, bureau score), the backend function gains parameters and the 24× multiplier gets replaced with a LightGBM model trained on `loip/models/eligibility/`. The frontend stays unchanged — it already consumes `max_principal` from the API, and EMI math stays client-side.
