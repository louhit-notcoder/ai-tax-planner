from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.tax_engine import DeterministicTaxEngine, load_rule_release
from app.tax_engine.models import (
    AssetType, CapitalGainTransaction, DeductionClaims, EmploymentIncome,
    HouseProperty, OtherIncome, Regime, SalaryComponent, TaxFactSnapshot,
    TaxPayment, TaxpayerProfile,
)

ENGINE = DeterministicTaxEngine()
RULES = load_rule_release("AY2026_27_V3.0.0")


def snapshot(*, gross_salary="0", regime=Regime.NEW, deductions=None, other=None, properties=None, gains=None, payments=None):
    employments = []
    if Decimal(gross_salary):
        employments = [EmploymentIncome(
            employment_id="EMP-1", employer_name="Golden Employer",
            components=[SalaryComponent(code="GROSS", label="Gross salary", amount=Decimal(gross_salary))],
        )]
    return TaxFactSnapshot(
        snapshot_id="golden-snapshot", case_id="golden-case", selected_regime=regime,
        profile=TaxpayerProfile(date_of_birth=date(1990, 1, 1)), employments=employments,
        deductions=deductions or DeductionClaims(), other_income=other or OtherIncome(),
        house_properties=properties or [], capital_transactions=gains or [], tax_payments=payments or [],
        approved_fact_ids=["FACT-1"],
    )


@pytest.mark.parametrize(
    ("gross", "taxable", "liability"),
    [
        ("475000", "400000.00", "0.00"),
        ("875000", "800000.00", "0.00"),
        ("1274999", "1200000.00", "0.00"),
        ("1275000", "1200000.00", "0.00"),
        ("1275001", "1200000.00", "0.00"),
        ("1285000", "1210000.00", "10400.00"),
        ("2475000", "2400000.00", "312000.00"),
    ],
)
def test_new_regime_boundary_golden_cases(gross, taxable, liability):
    result = ENGINE.compute(snapshot(gross_salary=gross), RULES)
    assert result.new_regime.total_income == Decimal(taxable)
    assert result.new_regime.total_tax_liability == Decimal(liability)


def test_old_regime_80c_cap_and_salary_standard_deduction():
    facts = snapshot(gross_salary="1500000", regime=Regime.OLD, deductions=DeductionClaims(section_80c=Decimal("250000")))
    result = ENGINE.compute(facts, RULES)
    assert result.old_regime.deductions == Decimal("150000.00")
    assert result.old_regime.total_income == Decimal("1300000.00")


def test_two_house_properties_computed_individually():
    properties = [
        HouseProperty(property_id="P1", occupancy_type="SELF_OCCUPIED", interest_on_borrowed_capital=Decimal("240000")),
        HouseProperty(property_id="P2", occupancy_type="LET_OUT", gross_annual_value=Decimal("300000"), municipal_taxes_paid=Decimal("20000"), interest_on_borrowed_capital=Decimal("50000")),
    ]
    result = ENGINE.compute(snapshot(gross_salary="1275000", properties=properties), RULES)
    hp_lines = [line for line in result.calculation_lines if line.code.startswith("HP_")]
    assert len(hp_lines) == 4
    assert result.status.value in {"COMPLETE", "PROVISIONAL"}


def test_listed_equity_holding_period_and_112a_exemption():
    gain = CapitalGainTransaction(
        transaction_id="TX-1", asset_type=AssetType.LISTED_EQUITY,
        acquisition_date=date(2023, 1, 1), transfer_date=date(2025, 6, 1),
        sale_consideration=Decimal("500000"), actual_cost=Decimal("200000"),
        stt_paid_on_acquisition=True, stt_paid_on_transfer=True, listed=True,
    )
    result = ENGINE.compute(snapshot(gains=[gain]), RULES)
    bucket = next(item for item in result.buckets if item.code == "SECTION_112A")
    assert bucket.gross_amount == Decimal("300000.00")
    assert bucket.exemption_amount == Decimal("125000.00")
    assert bucket.taxable_amount == Decimal("175000.00")


def test_tax_payment_changes_refund_not_gross_liability():
    without = ENGINE.compute(snapshot(gross_salary="2100000"), RULES)
    with_tds = ENGINE.compute(snapshot(gross_salary="2100000", payments=[TaxPayment(payment_id="TDS1", payment_type="TDS", amount=Decimal("250000"))]), RULES)
    assert without.new_regime.total_tax_liability == with_tds.new_regime.total_tax_liability
    assert with_tds.new_regime.refund == Decimal("35500.00")


def test_same_snapshot_and_rules_are_byte_reproducible_at_result_level():
    facts = snapshot(gross_salary="1500000", deductions=DeductionClaims(section_80c=Decimal("150000")))
    first = ENGINE.compute(facts, RULES)
    second = ENGINE.compute(facts, RULES)
    assert first.result_hash == second.result_hash
    assert [line.line_id for line in first.calculation_lines] == [line.line_id for line in second.calculation_lines]
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_more_than_supported_scope_fails_closed():
    properties = [HouseProperty(property_id=f"P{i}", occupancy_type="SELF_OCCUPIED") for i in range(3)]
    result = ENGINE.compute(snapshot(properties=properties), RULES)
    assert result.status.value == "BLOCKED"
    assert any(item.code == "TOO_MANY_SELF_OCCUPIED_PROPERTIES" for item in result.blockers)
