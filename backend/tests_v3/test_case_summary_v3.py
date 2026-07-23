"""Unit tests for the consolidated case summary composer (pure logic)."""

from __future__ import annotations

from app.services.case_summary import compose_case_summary


def _fact(code, **value):
    return {"field_code": code, "value_json": value}


def test_summary_aggregates_income_and_flags_foreign_assets():
    facts = [
        _fact("SALARY.GROSS", amount="1250000", entity_key="TAN1"),
        _fact("OTHER_INCOME.BANK_INTEREST.TOTAL", amount="40000"),
        _fact("CAPITAL_GAIN.TRANSACTION", sale_consideration="300000"),
        _fact("CAPITAL_GAIN.TRANSACTION", sale_consideration="150000"),
        _fact("FOREIGN_ASSET", asset_id="FA_FIDELITY", schedule_fa_table="A2"),
        _fact("FOREIGN_INCOME.ITEM", item_id="FSI1", income_type="DIVIDEND"),
    ]
    summary = compose_case_summary(facts)
    assert "salary" in summary["sections"]
    assert "interest" in summary["sections"]
    # both capital-gains rows summed
    assert summary["sections"]["capital_gains"]["lines"][0]["amount"] == "450000"
    assert "foreign" in summary["sections"]
    # Schedule FA flag surfaced proactively
    assert any("Schedule FA" in f for f in summary["flags"])
    assert summary["has_data"] is True


def test_summary_asks_proactive_questions_for_gaps():
    # only salary present -> should ask about capital gains, interest, foreign, house property
    summary = compose_case_summary([_fact("SALARY.GROSS", amount="800000")])
    joined = " ".join(summary["suggested_questions"]).lower()
    assert "sell" in joined            # capital gains prompt
    assert "foreign" in joined         # Schedule FA prompt
    assert "capital_gains" not in summary["sections"]


def test_summary_surfaces_reconciliation_differences_as_flags():
    facts = [_fact("SALARY.GROSS", amount="1000000")]
    reconciliation = [
        {"category": "TDS", "category_label": "Tax deducted at source", "status": "DIFFERENCE", "difference": "12000"},
        {"category": "SALARY_INCOME", "category_label": "Salary income", "status": "MATCHED", "difference": "0"},
    ]
    summary = compose_case_summary(facts, reconciliation, missing=["Form 26AS: not yet uploaded"])
    assert summary["reconciliation"]["matched"] == 1
    assert "Tax deducted at source" in summary["reconciliation"]["differences"]
    assert any("differs across sources by ₹12000" in f for f in summary["flags"])
    assert summary["missing"] == ["Form 26AS: not yet uploaded"]
