"""Unit tests for cross-document reconciliation (pure logic)."""

from __future__ import annotations

from app.services.reconciliation import compute_reconciliation


def _fact(field_code, amount=None, **value):
    v = dict(value)
    if amount is not None:
        v["amount"] = amount
    return {"field_code": field_code, "value_json": v}


def _by_category(results):
    return {r["category"]: r for r in results}


def test_matching_sources_are_marked_matched():
    facts = [
        _fact("SALARY.GROSS", "1250000"),                 # Form 16
        _fact("RECONCILIATION.AIS.SALARY", "1250000"),    # AIS agrees
    ]
    r = _by_category(compute_reconciliation(facts))["SALARY_INCOME"]
    assert r["status"] == "MATCHED"
    assert r["sources"] == {"AIS": "1250000", "Form 16": "1250000"}
    assert r["difference"] == "0"


def test_mismatched_sources_are_flagged_difference():
    facts = [
        _fact("TAX_PAYMENT.TDS.SALARY", "100000"),        # Form 16
        _fact("RECONCILIATION.AIS.TDS", "100000"),        # AIS
        _fact("RECONCILIATION.26AS.TDS", "112000"),       # 26AS disagrees -> attention
    ]
    r = _by_category(compute_reconciliation(facts))["TDS"]
    assert r["status"] == "DIFFERENCE"
    assert r["difference"] == "12000"
    assert set(r["sources"]) == {"Form 16", "AIS", "Form 26AS"}


def test_single_source_is_informational_not_a_mismatch():
    facts = [_fact("RECONCILIATION.AIS.DIVIDEND", "5000")]
    r = _by_category(compute_reconciliation(facts))["DIVIDEND_INCOME"]
    assert r["status"] == "SINGLE_SOURCE"


def test_broker_transactions_are_summed_before_comparing_to_ais():
    facts = [
        {"field_code": "CAPITAL_GAIN.TRANSACTION", "value_json": {"sale_consideration": "300000"}},
        {"field_code": "CAPITAL_GAIN.TRANSACTION", "value_json": {"sale_consideration": "150000"}},
        _fact("RECONCILIATION.AIS.SECURITIES_SALE", "450000"),
    ]
    r = _by_category(compute_reconciliation(facts))["SECURITIES_SALE"]
    assert r["sources"]["Broker"] == "450000"   # 300000 + 150000
    assert r["status"] == "MATCHED"


def test_small_difference_within_tolerance_is_matched():
    # a 1-rupee rounding gap should not nag the CA
    facts = [
        _fact("OTHER_INCOME.BANK_INTEREST.TOTAL", "40000"),
        _fact("RECONCILIATION.AIS.INTEREST", "40001"),
    ]
    assert _by_category(compute_reconciliation(facts))["INTEREST_INCOME"]["status"] == "MATCHED"


def test_differences_are_sorted_first():
    facts = [
        _fact("SALARY.GROSS", "1000000"), _fact("RECONCILIATION.AIS.SALARY", "1000000"),   # matched
        _fact("TAX_PAYMENT.TDS.SALARY", "50000"), _fact("RECONCILIATION.AIS.TDS", "90000"),  # difference
        _fact("RECONCILIATION.AIS.DIVIDEND", "5000"),  # single source
    ]
    results = compute_reconciliation(facts)
    assert results[0]["status"] == "DIFFERENCE"   # what the CA should look at, first
    assert results[-1]["status"] == "SINGLE_SOURCE"


def test_unmapped_fields_are_ignored():
    assert compute_reconciliation([_fact("SALARY.EMPLOYER.TAN", None, text="ABCD12345E")]) == []
