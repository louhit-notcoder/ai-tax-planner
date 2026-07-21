from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR

ZERO = Decimal("0")


def D(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money(value: Decimal) -> Decimal:
    return D(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def round_to_multiple(value: Decimal, multiple: Decimal) -> Decimal:
    if multiple <= ZERO:
        return money(value)
    quotient = (D(value) / multiple).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return money(quotient * multiple)


def completed_months(start: date, end: date) -> int:
    if end < start:
        return 0
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day < start.day:
        months -= 1
    return max(0, months)


def months_or_part(start: date, end: date) -> int:
    if end <= start:
        return 0
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day > start.day or (end.day == start.day and end > start):
        months += 1
    return max(1, months)


def slab_tax(income: Decimal, slabs: list[tuple[Decimal | None, Decimal]]) -> Decimal:
    remaining = max(ZERO, D(income))
    tax = ZERO
    for width, rate in slabs:
        if remaining <= ZERO:
            break
        taxable = remaining if width is None else min(remaining, width)
        tax += taxable * rate
        remaining -= taxable
    return money(tax)
