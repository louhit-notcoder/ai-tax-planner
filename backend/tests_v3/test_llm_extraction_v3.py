"""Unit tests for LLM-assisted document extraction.

These exercise the pure mapping and gating logic with a fake vision client, so
they run without a network call, an API key, or PDF rendering. The real model
call and PDF rasterisation are thin I/O wrappers exercised in staging.
"""

from __future__ import annotations

from decimal import Decimal

from app.document_adapters.llm_adapters import BankStatementPDFAdapter, BrokerCapitalGainsPDFAdapter, Form16LLMAdapter
from app.document_adapters.vision import parse_model_fields


class FakeVisionClient:
    def __init__(self, enabled: bool = True, rows=None):
        self._enabled = enabled
        self._rows = rows or []

    def enabled(self) -> bool:
        return self._enabled

    def extract(self, images, instruction, schema_hint):
        return self._rows


def _adapter(rows=None, enabled=True):
    return Form16LLMAdapter(client=FakeVisionClient(enabled=enabled, rows=rows))


def test_model_rows_become_evidence_linked_claims():
    # single image upload => one page (index 0); model reports where it read each value
    rows = [
        {"field_code": "SALARY.EMPLOYER.NAME", "value": "Acme Corp Pvt Ltd", "confidence": 0.98, "page_index": 0, "quote": "Name of Employer: Acme Corp Pvt Ltd"},
        {"field_code": "SALARY.EMPLOYER.TAN", "value": "BLRA12345C", "confidence": 0.99, "page_index": 0, "quote": "TAN: BLRA12345C"},
        {"field_code": "SALARY.GROSS", "value": "1250000", "confidence": 0.97, "page_index": 0, "quote": "Gross Salary 12,50,000"},
        {"field_code": "TAX_PAYMENT.TDS.SALARY", "value": "1,10,000", "confidence": 0.95, "page_index": 0, "quote": "Total tax deducted 1,10,000"},
    ]
    adapter = _adapter(rows)
    result = adapter.extract("form16.png", "image/png", b"")  # image path skips PDF rendering

    by_code = {c.field_code: c for c in result.claims}
    assert by_code["SALARY.GROSS"].value == {"amount": "1250000.00", "currency": "INR"}
    # comma-formatted rupee amount is normalised
    assert by_code["TAX_PAYMENT.TDS.SALARY"].value["amount"] == "110000.00"
    # page reference and quote survive for the CA to verify against
    assert by_code["SALARY.GROSS"].source.page_index == 0
    assert "12,50,000" in by_code["SALARY.GROSS"].source.original_text
    # employer entity is derived from TAN and bound onto every claim
    assert all(c.entity_key == "BLRA12345C" for c in result.claims)


def test_unknown_fields_and_blank_values_are_dropped():
    rows = [
        {"field_code": "SALARY.MADE_UP_FIELD", "value": "999", "confidence": 0.9},
        {"field_code": "SALARY.GROSS", "value": "", "confidence": 0.9},
        {"field_code": "SALARY.PROFESSIONAL_TAX", "value": "2400", "confidence": 0.9, "page_index": 1},
    ]
    claims = _adapter().claims_from_rows(rows, page_count=2)
    codes = {c.field_code for c in claims}
    assert codes == {"SALARY.PROFESSIONAL_TAX"}


def test_confidence_is_clamped_and_page_index_bounded():
    rows = [
        {"field_code": "SALARY.GROSS", "value": "500000", "confidence": 5, "page_index": 99},
        {"field_code": "SALARY.PROFESSIONAL_TAX", "value": "2400", "confidence": "not-a-number", "page_index": 0},
    ]
    claims = {c.field_code: c for c in _adapter().claims_from_rows(rows, page_count=2)}
    assert claims["SALARY.GROSS"].confidence == Decimal("0.99")   # clamped down from 5
    assert claims["SALARY.GROSS"].source.page_index is None        # 99 is out of range
    assert claims["SALARY.PROFESSIONAL_TAX"].confidence == Decimal("0.50")  # unparseable -> neutral


def test_missing_gross_and_impossible_exemptions_raise_warnings():
    # exemptions greater than gross is a classic OCR/extraction error the CA must catch
    rows = [
        {"field_code": "SALARY.GROSS", "value": "100000", "confidence": 0.9, "page_index": 0},
        {"field_code": "SALARY.SECTION10_EXEMPTIONS", "value": "200000", "confidence": 0.9, "page_index": 0},
    ]
    result = _adapter(rows).extract("form16.png", "image/png", b"")
    assert any("exceed gross" in w for w in result.warnings)

    result_missing = _adapter([]).extract("form16.png", "image/png", b"")
    assert any("Gross salary was not identified" in w for w in result_missing.warnings)


def test_supports_is_zero_when_model_unconfigured():
    # falls back to the deterministic regex adapter when no vision model is set
    assert _adapter(enabled=False).supports("form16.png", "image/png", b"") == Decimal("0")
    # a scanned Form 16 image (which regex cannot read) is claimed when enabled
    assert _adapter(enabled=True).supports("client_form16.png", "image/png", b"") == Decimal("0.85")


def test_parse_model_fields_tolerates_fences_and_envelopes():
    assert parse_model_fields('```json\n{"fields": [{"field_code": "X"}]}\n```') == [{"field_code": "X"}]
    assert parse_model_fields('[{"field_code": "Y"}]') == [{"field_code": "Y"}]
    assert parse_model_fields('{"items": [{"symbol": "Z"}]}') == [{"symbol": "Z"}]
    assert parse_model_fields("not json at all") == []
    assert parse_model_fields("") == []


# --- broker capital-gains PDF (line-item) extraction ------------------------

def _broker(rows=None, enabled=True):
    return BrokerCapitalGainsPDFAdapter(client=FakeVisionClient(enabled=enabled, rows=rows))


def test_broker_pdf_maps_transactions_with_asset_type_and_grandfathering():
    rows = [
        # equity (INE...), acquired before 31-Jan-2018 with a grandfathered FMV
        {"symbol": "INFY", "isin": "INE009A01021", "acquisition_date": "2015-05-10", "transfer_date": "2024-08-01",
         "sale_consideration": "300000", "actual_cost": "50000", "fmv_2018_01_31": "120000", "realized_gain": "250000",
         "stt_paid": "yes", "confidence": 0.96, "page_index": 0},
        # mutual fund (INF...), no grandfathering (bought after 2018)
        {"symbol": "Parag Parikh Flexi Cap Fund", "isin": "INF879O01019", "acquisition_date": "2021-01-01",
         "transfer_date": "2024-02-01", "sale_consideration": "150000", "actual_cost": "100000",
         "realized_gain": "50000", "confidence": 0.9, "page_index": 0},
    ]
    result = _broker(rows).extract("zerodha_pnl.pdf", "image/png", b"")
    assert len(result.claims) == 2
    eq, mf = result.claims

    assert eq.value["asset_type"] == "LISTED_EQUITY"
    assert eq.value["sale_consideration"] == "300000"
    assert eq.value["stt_paid_on_transfer"] is True
    assert eq.value["fmv_2018_01_31"] == "120000"       # grandfathered value captured
    assert eq.entity_key.startswith("TRADE_0_")

    assert mf.value["asset_type"] == "EQUITY_MUTUAL_FUND"
    assert "fmv_2018_01_31" not in mf.value             # acquired after 2018 -> not applicable


def test_broker_pdf_flags_realized_gain_mismatch():
    # stated realised gain disagrees with sale-cost-expenses => a column was misread
    rows = [
        {"symbol": "TCS", "isin": "INE467B01029", "acquisition_date": "2023-01-01", "transfer_date": "2024-01-02",
         "sale_consideration": "200000", "actual_cost": "150000", "realized_gain": "999999", "confidence": 0.9, "page_index": 0},
    ]
    result = _broker(rows).extract("pnl.pdf", "image/png", b"")
    claim = result.claims[0]
    crosscheck = next(v for v in claim.validations if v["code"] == "REALIZED_GAIN_CROSSCHECK")
    assert crosscheck["status"] == "REVIEW"
    assert any("does not match" in w for w in result.warnings)


def test_broker_pdf_skips_incomplete_rows_with_warning():
    rows = [
        {"symbol": "GOOD", "acquisition_date": "2023-01-01", "transfer_date": "2024-01-02", "sale_consideration": "100", "actual_cost": "50", "confidence": 0.9, "page_index": 0},
        {"symbol": "NO_DATES", "sale_consideration": "100", "actual_cost": "50"},  # missing dates -> skipped
    ]
    result = _broker(rows).extract("pnl.pdf", "image/png", b"")
    assert len(result.claims) == 1
    assert any("skipped" in w for w in result.warnings)


def test_broker_pdf_supports_gating():
    assert _broker(enabled=False).supports("pnl.pdf", "application/pdf", b"") == Decimal("0")
    assert _broker(enabled=True).supports("capital_gains_pnl.png", "image/png", b"") == Decimal("0.82")


# --- bank statement PDF (interest) extraction -------------------------------

def _bank(rows=None, enabled=True):
    return BankStatementPDFAdapter(client=FakeVisionClient(enabled=enabled, rows=rows))


def test_bank_pdf_extracts_interest_lines_and_computes_total():
    rows = [
        {"date": "2024-06-30", "description": "Savings interest credit", "amount": "1200.50", "confidence": 0.95, "page_index": 0},
        {"date": "2024-09-30", "description": "FD interest", "amount": "8000", "confidence": 0.9, "page_index": 0},
        {"date": "2024-07-01", "description": "not interest, ignored by amount<=0", "amount": "0", "confidence": 0.9},
    ]
    result = _bank(rows).extract("hdfc_statement.png", "image/png", b"")
    lines = [c for c in result.claims if c.field_code == "OTHER_INCOME.BANK_INTEREST.TRANSACTION"]
    total = next(c for c in result.claims if c.field_code == "OTHER_INCOME.BANK_INTEREST.TOTAL")
    assert len(lines) == 2                       # zero-amount row dropped
    assert total.value["amount"] == "9200.50"    # total computed here, not by the model
    # total carries the lowest line confidence (most conservative)
    assert total.confidence == Decimal("0.9")


def test_bank_pdf_no_interest_warns():
    result = _bank([]).extract("stmt.png", "image/png", b"")
    assert not any(c.field_code == "OTHER_INCOME.BANK_INTEREST.TOTAL" for c in result.claims)
    assert any("No interest credits" in w for w in result.warnings)


def test_bank_pdf_supports_gating():
    assert _bank(enabled=False).supports("stmt.pdf", "application/pdf", b"") == Decimal("0")
    assert _bank(enabled=True).supports("bank_passbook.png", "image/png", b"") == Decimal("0.80")
