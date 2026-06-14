"""Generate synthetic labeled datasets for Phase 1 tabular/graph ML models.

Produces four CSVs under data/training/:
  - income_synthetic.csv       (XGBoostWrapper, task="income_confidence")
  - risk_synthetic.csv         (XGBoostWrapper, task="risk_score")
  - affordability_synthetic.csv (LightGBMWrapper)
  - fraud_synthetic.csv        (GraphSAGEWrapper)

These are heuristic calibration targets, not outcomes derived from real
defaults/fraud cases (none exist yet). Each generator function documents the
formula used so the heuristic can be revisited once real labeled data is
available.

Run with: .venv-ml/bin/python -m scripts.training.generate_synthetic_dataset
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

import click

from scripts.generators.base import generate_aadhaar, generate_pan, random_employer, random_salary_components

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "training"

# Weighted distribution of "tamper types" applied to synthetic income cases,
# mirroring scripts/generators/generate_case.py's TAMPER_PRESETS keys.
TAMPER_WEIGHTS = {
    "clean": 0.55,
    "income_mismatch": 0.10,
    "income_inflated": 0.10,
    "identity_mismatch": 0.05,
    "dob_mismatch": 0.05,
    "employer_mismatch": 0.05,
    "pan_mismatch": 0.05,
    "document_forgery": 0.025,
    "synthetic_identity": 0.025,
    "missing_fields": 0.05,
}


def _clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _weighted_tamper(rng: random.Random) -> str:
    types = list(TAMPER_WEIGHTS.keys())
    weights = list(TAMPER_WEIGHTS.values())
    return rng.choices(types, weights=weights)[0]


def gen_income_row(rng: random.Random) -> dict:
    """XGBoostWrapper task="income_confidence" — features and label.

    Features: salary_slip_amount, bank_credit_amount, anomalies
    (matches domains/income_intel/processor.py's reconciliation inputs).

    True income = random_salary_components(tier)["net_pay"]. Clean cases have
    both amounts close to true income (small OCR-noise jitter). The
    income_mismatch/income_inflated tamper presets inflate the salary slip
    amount by 1.3x-1.8x (matching generate_salary_slip.py's real tamper
    logic), which the live processor flags as an anomaly when the relative
    discrepancy between salary slip and bank credit exceeds 0.3.

    Label = 1 - mean relative discrepancy from true income - 0.1 * anomalies,
    clipped to [0, 1]. Higher label = more confidence the reconciled income
    matches the true income.
    """
    _, tier = random_employer()
    salary = random_salary_components(tier)
    true_income = float(salary["net_pay"])

    tamper = _weighted_tamper(rng)

    salary_slip_amount = true_income * (1 + rng.gauss(0, 0.02))
    bank_credit_amount = true_income * (1 + rng.gauss(0, 0.02))

    if tamper in ("income_mismatch", "income_inflated"):
        factor = rng.uniform(1.3, 1.8)
        salary_slip_amount = true_income * factor
    elif tamper == "missing_fields":
        bank_credit_amount = 0.0

    anomalies = 0
    if salary_slip_amount > 0 and bank_credit_amount > 0:
        diff = abs(salary_slip_amount - bank_credit_amount)
        max_val = max(salary_slip_amount, bank_credit_amount)
        if max_val > 0 and diff / max_val > 0.3:
            anomalies += 1
            if salary_slip_amount > bank_credit_amount * 1.3:
                anomalies += 1
    elif bank_credit_amount == 0:
        anomalies += 1

    if true_income > 0:
        discrepancy = (
            abs(salary_slip_amount - true_income) + abs(bank_credit_amount - true_income)
        ) / (2 * true_income)
    else:
        discrepancy = 1.0

    label = _clip(1.0 - discrepancy - 0.1 * anomalies + rng.gauss(0, 0.02))

    return {
        "salary_slip_amount": round(salary_slip_amount, 2),
        "bank_credit_amount": round(bank_credit_amount, 2),
        "anomalies": anomalies,
        "label": round(label, 4),
    }


def gen_risk_row(rng: random.Random) -> dict:
    """XGBoostWrapper task="risk_score" — features and label.

    Features match the ensemble inputs in domains/risk_decisioning/processor.py:
    identity_confidence, income_confidence, foir, cibil_score_normalized,
    cashflow_stability, employment_tier, loan_to_income_ratio.

    Label is a hand-crafted CALIBRATION TARGET (no real default-outcome data
    exists). It is an approval-likelihood score consistent with the
    processor's thresholds: score >= 0.70 -> APPROVE, 0.40-0.70 -> REVIEW,
    < 0.40 -> REJECT (higher = better / more approvable).

    label = 0.25*identity_confidence + 0.25*income_confidence
          + 0.20*(1-foir) + 0.15*cibil_score_normalized
          + 0.10*cashflow_stability
          + 0.05*(1-(employment_tier-1)/4)
          - 0.15*min(loan_to_income_ratio/5, 1)
    plus small gaussian noise, clipped to [0, 1].
    """
    identity_confidence = rng.betavariate(8, 2)
    income_confidence = rng.betavariate(8, 2)
    foir = min(rng.betavariate(2, 3) * 1.3, 1.0)
    cibil_score_normalized = rng.betavariate(5, 2)
    cashflow_stability = rng.betavariate(5, 2)
    employment_tier = rng.choices([1, 2, 3, 4, 5], weights=[10, 25, 30, 20, 15])[0]
    loan_to_income_ratio = rng.uniform(0.5, 8.0)

    label = (
        0.25 * identity_confidence
        + 0.25 * income_confidence
        + 0.20 * (1 - foir)
        + 0.15 * cibil_score_normalized
        + 0.10 * cashflow_stability
        + 0.05 * (1 - (employment_tier - 1) / 4)
        - 0.15 * min(loan_to_income_ratio / 5.0, 1.0)
    )
    label = _clip(label + rng.gauss(0, 0.03))

    return {
        "identity_confidence": round(identity_confidence, 4),
        "income_confidence": round(income_confidence, 4),
        "foir": round(foir, 4),
        "cibil_score_normalized": round(cibil_score_normalized, 4),
        "cashflow_stability": round(cashflow_stability, 4),
        "employment_tier": employment_tier,
        "loan_to_income_ratio": round(loan_to_income_ratio, 4),
        "label": round(label, 4),
    }


def gen_affordability_row(rng: random.Random) -> dict:
    """LightGBMWrapper — features and label.

    Features match domains/affordability/processor.py's inputs to
    LightGBMWrapper.predict: foir, disposable_income, liquidity_score.

    NOTE: the live processor currently hardcodes liquidity_score=0.8 and
    cashflow_stability=0.8 as constants (not yet derived from bank-statement
    analysis). This dataset synthesizes a VARYING liquidity_score in [0, 1]
    so the model has a meaningful feature to learn from once the processor
    is updated to compute it from real data — a forward-looking calibration
    target, documented in docs/DATA_GUIDANCE_NOTES.md.

    label = 0.5*(1-foir) + 0.3*liquidity_score
          + 0.2*clip(disposable_income/50000, 0, 1)
    plus small gaussian noise, clipped to [0, 1].
    """
    foir = min(rng.betavariate(2, 3) * 1.3, 1.0)
    disposable_income = rng.uniform(-20000, 100000)
    liquidity_score = rng.betavariate(5, 2)

    label = (
        0.5 * (1 - foir)
        + 0.3 * liquidity_score
        + 0.2 * _clip(disposable_income / 50000.0)
    )
    label = _clip(label + rng.gauss(0, 0.03))

    return {
        "foir": round(foir, 4),
        "disposable_income": round(disposable_income, 2),
        "liquidity_score": round(liquidity_score, 4),
        "label": round(label, 4),
    }


def gen_fraud_dataset(rng: random.Random, n: int, ring_fraction: float = 0.08) -> list[dict]:
    """GraphSAGEWrapper — synthetic population graph and labels.

    Builds a population of n applications, each with a pan and aadhaar
    number. Most are unique. A fraction (ring_fraction) of applications are
    grouped into 2-3 member "rings" that share a pan or aadhaar value,
    mimicking the synthetic_identity tamper preset.

    Features (matching GraphSAGEWrapper's in-memory graph features):
    pan_match_count, aadhaar_match_count, total_degree (size of the union of
    pan- and aadhaar-sharing neighbors).

    Label = 1 if the application shares an identifier with >= 1 other
    application (total_degree > 0), else 0.
    """
    nodes = []
    for i in range(n):
        nodes.append({
            "application_id": f"APP-{i:05d}",
            "pan": generate_pan(),
            "aadhaar": generate_aadhaar(),
        })

    n_rings = max(1, int(n * ring_fraction / 2.5))
    for _ in range(n_rings):
        ring_size = rng.randint(2, 3)
        idx = rng.sample(range(n), ring_size)
        shared_field = rng.choice(["pan", "aadhaar"])
        shared_value = nodes[idx[0]][shared_field]
        for j in idx[1:]:
            nodes[j][shared_field] = shared_value

    pan_groups: dict[str, list[int]] = {}
    aadhaar_groups: dict[str, list[int]] = {}
    for i, node in enumerate(nodes):
        pan_groups.setdefault(node["pan"], []).append(i)
        aadhaar_groups.setdefault(node["aadhaar"], []).append(i)

    rows = []
    for i, node in enumerate(nodes):
        pan_match_count = len(pan_groups[node["pan"]]) - 1
        aadhaar_match_count = len(aadhaar_groups[node["aadhaar"]]) - 1
        neighbor_ids = set(pan_groups[node["pan"]]) | set(aadhaar_groups[node["aadhaar"]])
        neighbor_ids.discard(i)
        total_degree = len(neighbor_ids)
        label = 1 if total_degree > 0 else 0
        rows.append({
            "pan_match_count": pan_match_count,
            "aadhaar_match_count": aadhaar_match_count,
            "total_degree": total_degree,
            "label": label,
        })
    return rows


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


@click.command()
@click.option("--count", default=1000, show_default=True, help="Number of rows per tabular dataset.")
@click.option("--seed", default=42, show_default=True, help="Random seed for reproducibility.")
@click.option("--output-dir", default=str(OUTPUT_DIR), show_default=True, help="Output directory for CSVs.")
def main(count: int, seed: int, output_dir: str) -> None:
    rng = random.Random(seed)
    random.seed(seed)  # base.py generators (generate_pan, generate_aadhaar, etc.) use the global RNG
    out_dir = Path(output_dir)

    income_rows = [gen_income_row(rng) for _ in range(count)]
    risk_rows = [gen_risk_row(rng) for _ in range(count)]
    affordability_rows = [gen_affordability_row(rng) for _ in range(count)]
    fraud_rows = gen_fraud_dataset(rng, n=count)

    _write_csv(out_dir / "income_synthetic.csv", income_rows)
    _write_csv(out_dir / "risk_synthetic.csv", risk_rows)
    _write_csv(out_dir / "affordability_synthetic.csv", affordability_rows)
    _write_csv(out_dir / "fraud_synthetic.csv", fraud_rows)

    click.echo(f"Wrote {count} rows each to {out_dir}/{{income,risk,affordability}}_synthetic.csv")
    click.echo(f"Wrote {len(fraud_rows)} rows to {out_dir}/fraud_synthetic.csv "
               f"({sum(r['label'] for r in fraud_rows)} positive)")


if __name__ == "__main__":
    main()
