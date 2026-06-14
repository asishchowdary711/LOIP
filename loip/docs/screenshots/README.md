# UI Screenshots

Full-page captures of the LOIP review console (mock-mode demo data).
Regenerate with the API running on port 8000:

```bash
PYTHONPATH=/workspaces/LOIP loip/.venv/bin/python -m scripts.capture_screenshots
```

| File | Page | What it shows |
|---|---|---|
| `01_dashboard.png` | `/ui` | Decision mix (2 approve / 3 review / 2 reject), avg FOIR/CIBIL, recent applications |
| `02_review_queue.png` | `/ui/queue` | Queue sorted by risk; FOIR, CIBIL, primary reason code, status, age |
| `03_review_detail.png` | `/ui/review/{id}` | Review case — identity/income/affordability/bureau, evidence chains, SHAP, AI copilot, override form |
| `04_review_detail_reject.png` | `/ui/review/{id}` | A rejected case (FOIR exceeded) detail view |
| `05_api_docs.png` | `/docs` | Swagger API explorer — all endpoint groups + schemas |
