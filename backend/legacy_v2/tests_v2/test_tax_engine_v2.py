from decimal import Decimal

from tax_engine import CapitalGainsInput, TaxComputeRequest, engine


def test_new_regime_rebate_zero_tax_at_twelve_lakh_taxable_income():
    result = engine.compute(TaxComputeRequest(gross_salary=Decimal("1275000")))
    assert result.taxable_income_new == Decimal("1200000.00")
    assert result.base_tax_new == Decimal("60000.00")
    assert result.rebate_new == Decimal("60000.00")
    assert result.tax_liability_new == Decimal("0.00")
    assert result.computation_status == "COMPLETE"


def test_new_regime_contains_25_percent_slab():
    result = engine.compute(TaxComputeRequest(gross_salary=Decimal("2475000")))
    assert result.taxable_income_new == Decimal("2400000.00")
    assert result.base_tax_new == Decimal("300000.00")
    assert any(row.rate == Decimal("0.25") and row.taxable_amount == Decimal("400000.00") for row in result.slabs_new)


def test_new_regime_marginal_relief_above_rebate_threshold():
    result = engine.compute(TaxComputeRequest(gross_salary=Decimal("1285000")))
    assert result.taxable_income_new == Decimal("1210000.00")
    assert result.base_tax_new == Decimal("61500.00")
    assert result.marginal_relief_87a_new == Decimal("51500.00")
    assert result.gross_tax_liability_new == Decimal("10400.00")
    assert result.tax_liability_new == Decimal("10400.00")


def test_property_capital_gain_fails_closed():
    result = engine.compute(TaxComputeRequest(
        capital_gains=CapitalGainsInput(property_sale_price=Decimal("5000000"), property_purchase_price=Decimal("2000000"))
    ))
    assert result.computation_status == "BLOCKED"
    assert result.property_gains == Decimal("0")
    assert any(item["code"] == "PROPERTY_GAIN_UNSUPPORTED" for item in result.blockers)


def test_special_rate_income_is_separate_and_not_rebated():
    result = engine.compute(TaxComputeRequest(
        capital_gains=CapitalGainsInput(stcg_equity=Decimal("100000"))
    ))
    assert result.stcg_tax == Decimal("20000.00")
    assert result.tax_liability_new == Decimal("20800.00")
    assert any(item["code"] == "SPECIAL_RATE_REBATE_REVIEW" for item in result.warnings)
    assert result.computation_status == "PROVISIONAL"


def test_tax_credits_compute_payable_and_refund():
    result = engine.compute(TaxComputeRequest(gross_salary=Decimal("2100000"), tds_deducted=Decimal("250000")))
    assert result.tax_liability_new == Decimal("214500.00")
    assert result.amount_payable_new == Decimal("0.00")
    assert result.refund_new == Decimal("35500.00")


def test_same_inputs_produce_same_hashes():
    request = TaxComputeRequest(gross_salary=Decimal("1500000"), deductions_80c=Decimal("150000"))
    first = engine.compute(request)
    second = engine.compute(request)
    assert first.input_hash == second.input_hash
    assert first.result_hash == second.result_hash


def test_total_income_above_fifty_lakh_is_blocked_for_surcharge_review():
    result = engine.compute(TaxComputeRequest(gross_salary=Decimal("6000000")))
    assert result.computation_status == "BLOCKED"
    assert any(item["code"] == "SURCHARGE_SCOPE_EXCEEDED" for item in result.blockers)
