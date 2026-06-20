# Loan Eligibility Widget — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an inline loan eligibility widget to the `/apply` page so users enter salary, pick tenure, drag a principal slider, and see live EMI — then click to pre-fill the application form.

**Architecture:** New `calculate_eligibility()` function in `loip/services/eligibility.py`, called by a new `GET /apply/eligibility` endpoint added to `loip/web/routes/demo.py`. The `/apply` Jinja2 template (`apply.html`) gets a new HTML/CSS/JS widget block above the existing form. EMI is computed client-side for instant slider feedback.

**Tech Stack:** Python 3.12, FastAPI, Jinja2 templates, vanilla JS (no React — `/apply` is a single Jinja2 HTML file)

## Global Constraints

- Interest rate: fixed 12% p.a. for demo
- Max principal: `min(salary × 24, ₹40,00,000)`
- Salary range: ₹10,000 – ₹10,00,00,000
- Tenure options: 12, 24, 36, 48, 60 months
- No database, no auth, no ML
- Follow existing code style in `demo.py` and `apply.html`

---

### Task 1: Eligibility service function + unit tests

**Files:**
- Create: `loip/services/__init__.py`
- Create: `loip/services/eligibility.py`
- Create: `tests/__init__.py`
- Create: `tests/test_eligibility.py`

**Interfaces:**
- Consumes: nothing
- Produces: `calculate_eligibility(salary: int) -> dict` returning `{"salary": int, "max_principal": int, "multiplier": 24, "rate_pa": 0.12, "tenure_months": [12,24,36,48,60]}`; raises `ValueError` for out-of-range salary

- [ ] **Step 1: Write the failing tests**

Create `tests/__init__.py` (empty) and `tests/test_eligibility.py`:

```python
import pytest
from loip.services.eligibility import calculate_eligibility


def test_basic_salary():
    result = calculate_eligibility(25_000)
    assert result["salary"] == 25_000
    assert result["max_principal"] == 600_000
    assert result["multiplier"] == 24
    assert result["rate_pa"] == 0.12
    assert result["tenure_months"] == [12, 24, 36, 48, 60]


def test_high_salary_hits_cap():
    result = calculate_eligibility(200_000)
    assert result["max_principal"] == 40_00_000


def test_exact_cap_boundary():
    # salary * 24 == 40L exactly at salary = 166667
    result = calculate_eligibility(166_667)
    assert result["max_principal"] == min(166_667 * 24, 40_00_000)


def test_salary_below_minimum_raises():
    with pytest.raises(ValueError, match="Salary out of range"):
        calculate_eligibility(9_999)


def test_salary_zero_raises():
    with pytest.raises(ValueError, match="Salary out of range"):
        calculate_eligibility(0)


def test_salary_negative_raises():
    with pytest.raises(ValueError, match="Salary out of range"):
        calculate_eligibility(-50_000)


def test_salary_above_maximum_raises():
    with pytest.raises(ValueError, match="Salary out of range"):
        calculate_eligibility(10_00_00_001)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd loip && ../.venv/bin/python -m pytest ../tests/test_eligibility.py -v` (or from repo root with the venv's pytest)

Expected: `ModuleNotFoundError: No module named 'loip.services.eligibility'`

- [ ] **Step 3: Write the implementation**

Create `loip/services/__init__.py` (empty file).

Create `loip/services/eligibility.py`:

```python
def calculate_eligibility(salary: int) -> dict:
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd loip && ../.venv/bin/python -m pytest ../tests/test_eligibility.py -v`

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add loip/services/__init__.py loip/services/eligibility.py tests/__init__.py tests/test_eligibility.py
git commit -m "feat: add eligibility service with unit tests"
```

---

### Task 2: FastAPI endpoint + route tests

**Files:**
- Modify: `loip/web/routes/demo.py` (add `/apply/eligibility` GET handler)
- Create: `tests/test_eligibility_route.py`

**Interfaces:**
- Consumes: `calculate_eligibility(salary: int)` from Task 1
- Produces: `GET /apply/eligibility?salary=<int>` → JSON `{"salary", "max_principal", "multiplier", "rate_pa", "tenure_months"}`; 422 on invalid input

- [ ] **Step 1: Write the failing route tests**

Create `tests/test_eligibility_route.py`:

```python
import pytest
from fastapi.testclient import TestClient
from loip.web.api import app

client = TestClient(app)


def test_eligibility_valid_salary():
    resp = client.get("/apply/eligibility", params={"salary": 35_000})
    assert resp.status_code == 200
    data = resp.json()
    assert data["salary"] == 35_000
    assert data["max_principal"] == 840_000
    assert data["rate_pa"] == 0.12
    assert data["tenure_months"] == [12, 24, 36, 48, 60]


def test_eligibility_salary_too_low():
    resp = client.get("/apply/eligibility", params={"salary": 5_000})
    assert resp.status_code == 422


def test_eligibility_missing_salary():
    resp = client.get("/apply/eligibility")
    assert resp.status_code == 422


def test_eligibility_non_numeric():
    resp = client.get("/apply/eligibility", params={"salary": "abc"})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd loip && ../.venv/bin/python -m pytest ../tests/test_eligibility_route.py -v`

Expected: FAIL — 404 (route doesn't exist yet)

- [ ] **Step 3: Add the route to demo.py**

Add this at the end of the route handlers in `loip/web/routes/demo.py` (before the final line of the file), after the existing imports:

```python
from loip.services.eligibility import calculate_eligibility
```

And the route handler:

```python
@router.get("/eligibility")
async def loan_eligibility(salary: int):
    try:
        result = calculate_eligibility(salary)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return JSONResponse(result)
```

Note: `router` already has `prefix="/apply"`, so this becomes `GET /apply/eligibility`. `HTTPException` and `JSONResponse` are already imported in `demo.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd loip && ../.venv/bin/python -m pytest ../tests/test_eligibility_route.py -v`

Expected: 4 passed

- [ ] **Step 5: Run Task 1 tests too (regression check)**

Run: `cd loip && ../.venv/bin/python -m pytest ../tests/ -v`

Expected: 11 passed (7 from Task 1 + 4 from Task 2)

- [ ] **Step 6: Commit**

```bash
git add loip/web/routes/demo.py tests/test_eligibility_route.py
git commit -m "feat: add GET /apply/eligibility endpoint"
```

---

### Task 3: Eligibility widget in apply.html

**Files:**
- Modify: `loip/web/templates/apply.html` (add CSS, HTML, and JS for the widget)

**Interfaces:**
- Consumes: `GET /apply/eligibility?salary=<int>` from Task 2
- Produces: Pre-fills `monthly_income` and `loan_amount` form fields on CTA click

This task adds three blocks to `apply.html`:
1. CSS styles (in the `<style>` block)
2. HTML widget (between the mode bar and the form)
3. JS logic (in the `<script>` block)

- [ ] **Step 1: Add CSS for the eligibility widget**

Add these styles inside the existing `<style>` block, before the closing `</style>` tag (line 292), after the `@media` rule:

```css
/* Eligibility Widget */
.elig{
  padding:28px 32px;border-bottom:1px solid var(--line);
  background:linear-gradient(135deg, rgba(16,185,129,0.03) 0%, rgba(99,102,241,0.03) 100%);
}
.elig .elig-input{
  display:flex;gap:14px;align-items:flex-end;
}
.elig .elig-input .field{flex:1}
.elig .elig-result{
  display:none;margin-top:22px;
  animation: fadeIn 0.4s ease-out;
}
.elig .elig-result.show{display:block}
.elig .elig-headline{
  font-size:1.15rem;font-weight:800;color:var(--text-heading);
  margin-bottom:18px;
}
.elig .elig-headline span{color:var(--accent-2)}
.elig .tenure-btns{
  display:flex;gap:8px;margin-bottom:18px;
}
.elig .tenure-btns button{
  flex:1;padding:10px 0;border:1.5px solid var(--line);border-radius:10px;
  background:var(--panel-2);color:var(--muted);font-size:.88rem;font-weight:700;
  cursor:pointer;transition:all .2s;font-family:inherit;
}
.elig .tenure-btns button:hover{border-color:var(--accent);color:var(--text)}
.elig .tenure-btns button.active{
  border-color:var(--accent);background:var(--accent-soft);color:var(--accent-2);
  box-shadow:0 0 8px var(--accent-soft);
}
.elig .slider-row{
  display:flex;align-items:center;gap:16px;margin-bottom:14px;
}
.elig .slider-row input[type=range]{
  flex:1;-webkit-appearance:none;appearance:none;height:6px;
  background:var(--panel-2);border-radius:3px;outline:none;border:1px solid var(--line);
}
.elig .slider-row input[type=range]::-webkit-slider-thumb{
  -webkit-appearance:none;width:22px;height:22px;border-radius:50%;
  background:var(--accent);cursor:pointer;border:3px solid var(--bg);
  box-shadow:0 0 8px var(--accent-soft);
}
.elig .slider-row .slider-val{
  font-size:1.1rem;font-weight:800;color:var(--accent-2);
  min-width:120px;text-align:right;font-family:'JetBrains Mono',monospace;
}
.elig .emi-display{
  display:flex;gap:24px;align-items:baseline;margin:18px 0;
  padding:16px 20px;background:var(--panel-2);border:1px solid var(--line);
  border-radius:12px;
}
.elig .emi-display .emi-main{
  font-size:1.6rem;font-weight:800;color:var(--text-heading);
  font-family:'JetBrains Mono',monospace;
}
.elig .emi-display .emi-label{
  font-size:.82rem;color:var(--muted);font-weight:600;
}
.elig .emi-display .emi-interest{
  font-size:.88rem;color:var(--muted);font-weight:500;
}
.elig .elig-cta{
  width:100%;padding:14px;border:none;border-radius:10px;
  background:linear-gradient(135deg, var(--accent) 0%, var(--accent-2) 100%);
  color:#fff;font-size:1rem;font-weight:700;cursor:pointer;
  transition:all .3s;font-family:inherit;
  box-shadow:0 4px 14px var(--accent-soft);
}
.elig .elig-cta:hover{
  transform:translateY(-1px);
  box-shadow:0 6px 18px rgba(16,185,129,0.3);
}
.elig .elig-error{
  color:var(--bad);font-size:.82rem;margin-top:8px;font-weight:500;
}
```

- [ ] **Step 2: Add HTML widget block**

Insert this HTML after the mode bar `<div>` (after line 302, `<div class="modebar" ... </div>`) and before `<!-- ============ FORM VIEW ============ -->` (line 304):

```html
<!-- ============ ELIGIBILITY WIDGET ============ -->
<div class="elig" id="eligWidget">
  <div class="section-title"><span class="sq"></span> Check your eligibility</div>
  <div class="elig-input">
    <div class="field"><label>Monthly net salary (₹)</label>
      <input id="eligSalary" type="number" placeholder="e.g. 50000" min="10000">
    </div>
    <button type="button" class="btn" id="eligCheckBtn" style="height:47px;margin-bottom:1px;padding:0 24px;font-size:.9rem">Check</button>
  </div>
  <div class="elig-error" id="eligError"></div>
  <div class="elig-result" id="eligResult">
    <div class="elig-headline">You're eligible for up to <span id="eligMax">—</span></div>
    <div style="font-size:.82rem;color:var(--muted);font-weight:600;margin-bottom:10px">Select tenure</div>
    <div class="tenure-btns" id="tenureBtns"></div>
    <div style="font-size:.82rem;color:var(--muted);font-weight:600;margin-bottom:10px">Choose loan amount</div>
    <div class="slider-row">
      <span style="font-size:.78rem;color:var(--faint)">₹50K</span>
      <input type="range" id="eligSlider" min="50000" step="10000">
      <span class="slider-val" id="eligSliderVal">—</span>
    </div>
    <div class="emi-display">
      <div>
        <div class="emi-label">Monthly EMI</div>
        <div class="emi-main" id="eligEmi">—</div>
      </div>
      <div>
        <div class="emi-label">Total interest</div>
        <div class="emi-interest" id="eligInterest">—</div>
      </div>
      <div>
        <div class="emi-label">Rate</div>
        <div class="emi-interest">12% p.a.</div>
      </div>
    </div>
    <button type="button" class="elig-cta" id="eligCta">Apply for — over — →</button>
  </div>
</div>
```

- [ ] **Step 3: Add JS logic**

Add this JavaScript inside the existing `<script>` block, right after the opening `<script>` tag (line 392) and before the `const SLOTS=` line:

```javascript
/* ---------- eligibility widget ---------- */
(function(){
  const salaryInput = document.getElementById('eligSalary');
  const checkBtn = document.getElementById('eligCheckBtn');
  const resultDiv = document.getElementById('eligResult');
  const errorDiv = document.getElementById('eligError');
  const maxSpan = document.getElementById('eligMax');
  const slider = document.getElementById('eligSlider');
  const sliderVal = document.getElementById('eligSliderVal');
  const emiEl = document.getElementById('eligEmi');
  const interestEl = document.getElementById('eligInterest');
  const ctaBtn = document.getElementById('eligCta');
  const tenureBtnsDiv = document.getElementById('tenureBtns');

  let eligData = null;
  let selectedTenure = 36;

  function fmtInr(n) {
    return '₹' + Math.round(n).toLocaleString('en-IN');
  }

  function calcEmi(P, ratePA, months) {
    const r = ratePA / 12;
    if (r === 0) return P / months;
    return P * r * Math.pow(1 + r, months) / (Math.pow(1 + r, months) - 1);
  }

  function updateEmi() {
    if (!eligData) return;
    const P = parseInt(slider.value);
    const emi = calcEmi(P, eligData.rate_pa, selectedTenure);
    const totalInterest = (emi * selectedTenure) - P;
    sliderVal.textContent = fmtInr(P);
    emiEl.textContent = fmtInr(emi) + '/mo';
    interestEl.textContent = fmtInr(totalInterest);
    ctaBtn.textContent = 'Apply for ' + fmtInr(P) + ' over ' + selectedTenure + ' months →';
  }

  function renderTenureButtons(tenures) {
    tenureBtnsDiv.innerHTML = '';
    tenures.forEach(function(t) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = t + ' mo';
      if (t === selectedTenure) btn.className = 'active';
      btn.addEventListener('click', function() {
        selectedTenure = t;
        tenureBtnsDiv.querySelectorAll('button').forEach(function(b) { b.className = ''; });
        btn.className = 'active';
        updateEmi();
      });
      tenureBtnsDiv.appendChild(btn);
    });
  }

  async function checkEligibility() {
    errorDiv.textContent = '';
    resultDiv.classList.remove('show');
    const salary = parseInt(salaryInput.value);
    if (!salary || salary < 10000) {
      errorDiv.textContent = 'Minimum salary ₹10,000 for personal loan eligibility';
      return;
    }
    try {
      const resp = await fetch('/apply/eligibility?salary=' + salary);
      if (!resp.ok) {
        const err = await resp.json().catch(function() { return {}; });
        errorDiv.textContent = err.detail || 'Please enter a valid salary';
        return;
      }
      eligData = await resp.json();
      maxSpan.textContent = fmtInr(eligData.max_principal);
      slider.max = eligData.max_principal;
      slider.value = Math.round(eligData.max_principal * 0.6);
      selectedTenure = 36;
      renderTenureButtons(eligData.tenure_months);
      resultDiv.classList.add('show');
      updateEmi();
    } catch (e) {
      errorDiv.textContent = 'Could not check eligibility. Please try again.';
    }
  }

  checkBtn.addEventListener('click', checkEligibility);
  salaryInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') { e.preventDefault(); checkEligibility(); }
  });
  slider.addEventListener('input', updateEmi);

  ctaBtn.addEventListener('click', function() {
    if (!eligData) return;
    const P = parseInt(slider.value);
    const incomeField = document.querySelector('[name="monthly_income"]');
    const amountField = document.querySelector('[name="loan_amount"]');
    if (incomeField) incomeField.value = eligData.salary;
    if (amountField) amountField.value = P;
    incomeField.dispatchEvent(new Event('input', {bubbles: true}));
    amountField.dispatchEvent(new Event('input', {bubbles: true}));
    document.getElementById('formView').scrollIntoView({behavior: 'smooth'});
  });
})();
```

- [ ] **Step 4: Manual verification**

Start the demo server:
```bash
./start-demo.sh
```

Open `http://localhost:8000/apply` in a browser. Verify:
1. Salary input and "Check" button appear above the form
2. Enter 50000 → widget expands showing "₹12,00,000" max
3. Tenure buttons work (12/24/36/48/60), 36 is default
4. Slider drags from ₹50K to ₹12L, EMI updates live
5. Click CTA → form's monthly_income = 50000, loan_amount = slider value
6. Enter 5000 → error "Minimum salary ₹10,000"
7. Enter 200000 → max capped at ₹40,00,000
8. Progress bar still works correctly after pre-fill

- [ ] **Step 5: Commit**

```bash
git add loip/web/templates/apply.html
git commit -m "feat: add loan eligibility widget to /apply page"
```

---
