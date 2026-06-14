"""Self-employed income reconstruction (build-plan §7.2).

Exercises the reconciliation logic directly with synthetic extracted data
(independent of OCR/VLM extraction).
"""

from loip.domains.income_intel.processor import IncomeIntelligenceProcessor


def _income(extracted, segment):
    return IncomeIntelligenceProcessor(mock_mode=True).process_income(
        "SE-TEST", extracted, segment=segment
    )


def test_two_year_itr_averaging():
    """ITR fy1 (0.90) weighted above fy2 (0.80): reconciled income sits between
    the two years, closer to fy1."""
    result = _income(
        {"itr": {"total_income": "1200000"}, "itr_fy2": {"total_income": "800000"}},
        "self_employed",
    )
    sources = {s.source_name: s.trust_weight for s in result.income_sources}
    assert sources["itr"] == 0.90
    assert sources["itr_fy2"] == 0.80
    # weighted avg = (1.2M*0.9 + 0.8M*0.8) / (0.9+0.8) = 1,011,764...
    assert 1_000_000 < result.reconciled_annual_income < 1_020_000


def test_gst_profit_margin_fallback():
    """With only GST turnover, net income ≈ 25% of turnover."""
    result = _income(
        {"gst_return": {"turnover_b2b": "3000000", "turnover_b2c": "1000000"}},
        "self_employed",
    )
    gst = next(s for s in result.income_sources if s.source_name == "gst_return")
    assert gst.annual_amount == 4_000_000 * 0.25
    assert gst.trust_weight == 0.75


def test_self_employed_bank_weight_lower_than_salaried():
    se = _income({"bank_statement": {"salary_credits": [{"amount": 100000, "date": "01/01/2026", "narration": "UPI"}]}}, "self_employed")
    sal = _income({"bank_statement": {"salary_credits": [{"amount": 100000, "date": "01/01/2026", "narration": "SALARY"}]}}, "salaried")
    se_bank = next(s for s in se.income_sources if s.source_name == "bank_statement")
    sal_bank = next(s for s in sal.income_sources if s.source_name == "bank_statement")
    assert se_bank.trust_weight == 0.65
    assert sal_bank.trust_weight == 0.75
