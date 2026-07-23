"""Consolidated case summary (pure logic).

After a CA dumps a batch of documents, this composes ONE summary across all of
them — what income/assets were found, how the independent sources reconcile,
what is still missing, and what to proactively ask the client — instead of a
per-document blurb. Pure and unit-testable; the service layer loads the data.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

# field_code -> (section key, human label, amount key in value_json)
_INCOME_FIELDS: dict[str, tuple[str, str, str]] = {
    "SALARY.GROSS": ("salary", "Salary (Form 16)", "amount"),
    "RECONCILIATION.AIS.SALARY": ("salary", "Salary (AIS)", "amount"),
    "OTHER_INCOME.BANK_INTEREST.TOTAL": ("interest", "Bank interest", "amount"),
    "RECONCILIATION.AIS.INTEREST": ("interest", "Interest (AIS)", "amount"),
    "RECONCILIATION.AIS.DIVIDEND": ("dividend", "Dividend (AIS)", "amount"),
    "TAX_PAYMENT.TDS.SALARY": ("tds", "TDS on salary (Form 16)", "amount"),
    "RECONCILIATION.AIS.TDS": ("tds", "TDS (AIS)", "amount"),
    "RECONCILIATION.26AS.TDS": ("tds", "TDS (Form 26AS)", "amount"),
}

# Common items a CA should chase if the documents don't already show them.
_PROACTIVE_QUESTIONS = {
    "capital_gains": "Did the client sell any shares, mutual funds, or property this year? (no capital-gains statement seen)",
    "interest": "Any savings/FD interest? Upload the bank statement or confirm the AIS interest figure.",
    "foreign": "Any foreign bank/brokerage accounts, RSUs, ESOPs, or US/overseas investments? (needed for Schedule FA)",
    "house_property": "Does the client own house property or pay a home loan? (no house-property data seen)",
    "deductions": "Any 80C / 80D / NPS / donations to claim under the old regime?",
}


def _dec(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def compose_case_summary(
    facts: Iterable[dict[str, Any]],
    reconciliation: Iterable[dict[str, Any]] = (),
    missing: Iterable[str] = (),
    documents: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a consolidated summary payload.

    ``facts`` is an iterable of ``{"field_code", "value_json"}`` (the reviewed or
    extracted facts). ``reconciliation`` is the output of compute_reconciliation.
    ``documents`` reports processing status (counts by state + extraction
    warnings) so the summary can explain WHY there is no data yet.
    """
    sections: dict[str, dict[str, Any]] = {}
    capital_gain_count = 0
    capital_gain_total = Decimal("0")
    foreign_asset_count = 0
    foreign_income_count = 0

    for fact in facts:
        code = fact.get("field_code", "")
        value = fact.get("value_json") or {}
        if code == "CAPITAL_GAIN.TRANSACTION":
            capital_gain_count += 1
            capital_gain_total += _dec(value.get("sale_consideration")) or Decimal("0")
            continue
        if code == "FOREIGN_ASSET":
            foreign_asset_count += 1
            continue
        if code == "FOREIGN_INCOME.ITEM":
            foreign_income_count += 1
            continue
        rule = _INCOME_FIELDS.get(code)
        if rule:
            key, label, amount_key = rule
            amount = _dec(value.get(amount_key))
            if amount is None:
                continue
            entry = sections.setdefault(key, {"lines": []})
            entry["lines"].append({"label": label, "amount": format(amount, "f")})

    if capital_gain_count:
        sections["capital_gains"] = {"lines": [{"label": f"{capital_gain_count} capital-gains transaction(s)", "amount": format(capital_gain_total, "f")}]}
    if foreign_asset_count or foreign_income_count:
        sections["foreign"] = {"lines": [{"label": f"{foreign_asset_count} foreign asset(s), {foreign_income_count} foreign income item(s)", "amount": None}]}

    recon = list(reconciliation)
    matched = [r for r in recon if r.get("status") == "MATCHED"]
    differences = [r for r in recon if r.get("status") == "DIFFERENCE"]

    flags: list[str] = []
    if foreign_asset_count or foreign_income_count:
        flags.append("Foreign assets/income present — Schedule FA and (for US tax withheld) Form 67 are required; convert USD amounts at the SBI TT buying rate.")
    for diff in differences:
        flags.append(f"Mismatch to verify: {diff.get('category_label', diff.get('category'))} differs across sources by ₹{diff.get('difference')}.")

    questions: list[str] = []
    if "capital_gains" not in sections:
        questions.append(_PROACTIVE_QUESTIONS["capital_gains"])
    if "interest" not in sections:
        questions.append(_PROACTIVE_QUESTIONS["interest"])
    if "foreign" not in sections:
        questions.append(_PROACTIVE_QUESTIONS["foreign"])
    if "house_property" not in sections:
        questions.append(_PROACTIVE_QUESTIONS["house_property"])

    return {
        "sections": sections,
        "reconciliation": {"matched": len(matched), "differences": [d.get("category_label", d.get("category")) for d in differences]},
        "missing": list(missing),
        "flags": flags,
        "suggested_questions": questions,
        "has_data": bool(sections),
    }
