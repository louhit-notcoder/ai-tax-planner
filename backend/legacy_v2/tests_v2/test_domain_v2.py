from decimal import Decimal

from production.form_eligibility import determine_form
from production.hashing import sha256_json
from production.itr_export import ExportBlockedError, build_official_itr_export
from production.legal_sources import search_tax_law


def money_fact(code, amount):
    return {"field_code": code, "value": {"amount": str(amount), "currency": "INR"}}


def test_itr1_eligibility_for_supported_salary_case():
    result = determine_form(
        filing={"selected_regime": "NEW", "residential_status": "RESIDENT_ORDINARILY_RESIDENT"},
        computation={"total_income_new": "1200000"},
        canonical_facts=[money_fact("SALARY.GROSS.AGGREGATE", 1275000)],
    )
    assert result["recommended_form"] == "ITR-1"
    assert result["status"] == "PROVISIONAL_REVIEW_REQUIRED"


def test_stcg_disqualifies_itr1():
    result = determine_form(
        filing={"selected_regime": "NEW", "residential_status": "RESIDENT_ORDINARILY_RESIDENT"},
        computation={"total_income_new": "900000"},
        canonical_facts=[money_fact("CAPITAL_GAIN.111A.AGGREGATE", 100000)],
    )
    assert result["recommended_form"] == "ITR-2"
    assert any("Short-term" in item for item in result["disqualifiers"])


def test_hashing_is_order_independent_for_dicts():
    assert sha256_json({"a": 1, "b": Decimal("2.00")}) == sha256_json({"b": Decimal("2.00"), "a": 1})


def test_official_export_is_fail_closed():
    try:
        build_official_itr_export(filing={})
        assert False, "Expected export to be blocked"
    except ExportBlockedError as exc:
        assert "disabled" in str(exc).lower()


def test_tax_law_search_only_returns_official_period_sources():
    results = search_tax_law("ITR 1 validation schema")
    assert results
    assert all(item["tax_period"] == "AY 2026-27" for item in results)
    assert all(item["official_url"].startswith("https://www.incometax.gov.in") for item in results)
