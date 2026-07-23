"""Cross-document reconciliation (pure logic).

Independent documents report the same economic figure — salary appears on the
Form 16 *and* in the AIS; TDS on the Form 16, the AIS *and* Form 26AS; interest
on the bank statement *and* the AIS; securities sales on the broker note *and*
the AIS. When those independent sources agree, the CA can trust-and-approve;
when they disagree, that is precisely the short list worth their attention.

This module is pure (no DB/IO) so it is directly unit-testable. The service
layer loads facts and persists the results.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

# field_code -> (reconciliation category, human source label, value_json key to read)
RECON_MAP: dict[str, tuple[str, str, str]] = {
    "SALARY.GROSS": ("SALARY_INCOME", "Form 16", "amount"),
    "RECONCILIATION.AIS.SALARY": ("SALARY_INCOME", "AIS", "amount"),
    "TAX_PAYMENT.TDS.SALARY": ("TDS", "Form 16", "amount"),
    "RECONCILIATION.AIS.TDS": ("TDS", "AIS", "amount"),
    "RECONCILIATION.26AS.TDS": ("TDS", "Form 26AS", "amount"),
    "OTHER_INCOME.BANK_INTEREST.TOTAL": ("INTEREST_INCOME", "Bank statement", "amount"),
    "RECONCILIATION.AIS.INTEREST": ("INTEREST_INCOME", "AIS", "amount"),
    "RECONCILIATION.AIS.DIVIDEND": ("DIVIDEND_INCOME", "AIS", "amount"),
    "RECONCILIATION.AIS.SECURITIES_SALE": ("SECURITIES_SALE", "AIS", "amount"),
    "CAPITAL_GAIN.TRANSACTION": ("SECURITIES_SALE", "Broker", "sale_consideration"),
}

CATEGORY_LABEL: dict[str, str] = {
    "SALARY_INCOME": "Salary income",
    "TDS": "Tax deducted at source",
    "INTEREST_INCOME": "Interest income",
    "DIVIDEND_INCOME": "Dividend income",
    "SECURITIES_SALE": "Sale of securities",
}

# Sort so the CA sees what needs attention first.
_STATUS_ORDER = {"DIFFERENCE": 0, "MATCHED": 1, "SINGLE_SOURCE": 2}


def _to_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def compute_reconciliation(
    facts: Iterable[dict[str, Any]],
    *,
    tolerance_ratio: Decimal = Decimal("0.01"),
    min_tolerance: Decimal = Decimal("1"),
) -> list[dict[str, Any]]:
    """Group facts into economic categories and compare independent sources.

    ``facts`` is an iterable of ``{"field_code": str, "value_json": dict}``.
    Amounts from the same source within a category are summed (e.g. AIS interest
    across several payers, or every broker sale row). Returns one row per
    category with the per-source totals, a status, and the spread.
    """
    buckets: dict[str, dict[str, Decimal]] = {}
    for fact in facts:
        rule = RECON_MAP.get(fact.get("field_code", ""))
        if not rule:
            continue
        category, source, amount_key = rule
        amount = _to_decimal((fact.get("value_json") or {}).get(amount_key))
        if amount is None:
            continue
        bucket = buckets.setdefault(category, {})
        bucket[source] = bucket.get(source, Decimal("0")) + amount

    results: list[dict[str, Any]] = []
    for category, sources in buckets.items():
        amounts = list(sources.values())
        spread = max(amounts) - min(amounts)
        if len(sources) < 2:
            status = "SINGLE_SOURCE"
        else:
            tolerance = max(min_tolerance, max(amounts) * tolerance_ratio)
            status = "MATCHED" if spread <= tolerance else "DIFFERENCE"
        results.append({
            "category": category,
            "category_label": CATEGORY_LABEL.get(category, category),
            "sources": {label: format(value, "f") for label, value in sorted(sources.items())},
            "status": status,
            "difference": format(spread, "f"),
        })

    results.sort(key=lambda row: (_STATUS_ORDER.get(row["status"], 9), row["category"]))
    return results
