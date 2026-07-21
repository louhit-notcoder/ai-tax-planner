"""Deterministic, Decimal-based tax engine for the limited AY 2026-27 V1 scope.

The public request/response fields preserve compatibility with the original UI while
adding a reproducible calculation trace, blockers, warnings, credits and hashes.
No database, network or LLM access occurs in this module.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from production.hashing import sha256_json
from production.rules import load_rule_release

D = Decimal
ZERO = D("0")
PAISE = D("0.01")
TEN = D("10")


def dec(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value in (None, ""):
        return ZERO
    return D(str(value))


def money(value: Decimal) -> Decimal:
    return value.quantize(PAISE, rounding=ROUND_HALF_UP)


def round_288b(value: Decimal) -> Decimal:
    return (value / TEN).quantize(D("1"), rounding=ROUND_HALF_UP) * TEN


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", json_encoders={Decimal: lambda v: float(v)})


class CapitalGainsInput(StrictModel):
    stcg_equity: Decimal = ZERO
    ltcg_equity: Decimal = ZERO
    property_sale_price: Decimal = ZERO
    property_purchase_price: Decimal = ZERO
    cii_year_purchase: int = 100
    cii_year_sale: int = 100

    @field_validator("stcg_equity", "ltcg_equity", "property_sale_price", "property_purchase_price")
    @classmethod
    def amounts_are_finite(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("amount must be finite")
        return value


class TaxComputeRequest(StrictModel):
    assessment_year: str = "AY 2026-27"
    residential_status: str = "RESIDENT_ORDINARILY_RESIDENT"
    age_category: str = "BELOW_60"
    gross_salary: Decimal = ZERO
    section_10_exemptions: Decimal = ZERO
    professional_tax: Decimal = ZERO
    deductions_80c: Decimal = ZERO
    deductions_80d: Decimal = ZERO
    other_deductions: Decimal = ZERO
    house_property_income: Decimal = ZERO
    other_income: Decimal = ZERO
    tds_deducted: Decimal = ZERO
    tcs_collected: Decimal = ZERO
    advance_tax: Decimal = ZERO
    self_assessment_tax: Decimal = ZERO
    has_business_income: bool = False
    has_foreign_assets: bool = False
    has_foreign_income: bool = False
    has_vda_income: bool = False
    has_unlisted_shares: bool = False
    capital_gains: CapitalGainsInput = Field(default_factory=CapitalGainsInput)


class SlabRow(StrictModel):
    label: str
    rate: Decimal
    taxable_amount: Decimal
    tax: Decimal


class CalculationLine(StrictModel):
    code: str
    label: str
    formula: str
    inputs: dict[str, Decimal | str | bool]
    result: Decimal
    rule_ids: list[str] = Field(default_factory=list)


class TaxComputationResult(StrictModel):
    computation_status: str
    assessment_year: str
    rule_release_id: str
    rule_bundle_hash: str
    input_hash: str
    result_hash: str
    blockers: list[dict]
    warnings: list[dict]
    assumptions: list[str]
    calculation_lines: list[CalculationLine]
    facts_used: list[str]
    facts_not_used: list[str]

    gross_salary: Decimal
    taxable_income_old: Decimal
    taxable_income_new: Decimal
    total_income_old: Decimal
    total_income_new: Decimal
    base_tax_old: Decimal
    base_tax_new: Decimal
    rebate_old: Decimal
    rebate_new: Decimal
    marginal_relief_87a_new: Decimal
    stcg_tax: Decimal
    ltcg_tax: Decimal
    property_gains: Decimal
    cess_old: Decimal
    cess_new: Decimal
    tax_liability_old: Decimal
    tax_liability_new: Decimal
    gross_tax_liability_old: Decimal
    gross_tax_liability_new: Decimal
    total_tax_credits: Decimal
    amount_payable_old: Decimal
    amount_payable_new: Decimal
    refund_old: Decimal
    refund_new: Decimal
    total_deductions_old: Decimal
    savings_with_recommended: Decimal
    recommended_regime: str
    slabs_old: list[SlabRow]
    slabs_new: list[SlabRow]


class DeterministicTaxEngine:
    RELEASE_ID = "AY2026_27_v1.0.0"

    @staticmethod
    def compute_hra_exemption(
        basic_salary: Decimal | float,
        hra_received: Decimal | float,
        rent_paid: Decimal | float,
        is_metro: bool,
    ) -> Decimal:
        basic, hra, rent = map(dec, (basic_salary, hra_received, rent_paid))
        limit_factor = D("0.50") if is_metro else D("0.40")
        return money(max(ZERO, min(hra, max(ZERO, rent - D("0.10") * basic), limit_factor * basic)))

    @staticmethod
    def _slab_tax(income: Decimal, slabs: list[list[Decimal]]) -> tuple[Decimal, list[SlabRow]]:
        remaining = max(ZERO, income)
        floor = ZERO
        tax = ZERO
        rows: list[SlabRow] = []
        for width, rate in slabs:
            if remaining <= ZERO:
                break
            taxable_slice = remaining if width.is_infinite() else min(remaining, width)
            slice_tax = taxable_slice * rate
            top = D("Infinity") if width.is_infinite() else floor + width
            label = f"Above {floor}" if top.is_infinite() else f"{floor}-{top}"
            rows.append(SlabRow(label=label, rate=rate, taxable_amount=money(taxable_slice), tax=money(slice_tax)))
            tax += slice_tax
            remaining -= taxable_slice
            floor = top
        return money(tax), rows

    @staticmethod
    def _rebate_old(total_income: Decimal, normal_tax: Decimal, special_tax: Decimal, rules: dict) -> Decimal:
        # Conservative limited-scope treatment: do not use rebate against special-rate tax.
        if total_income <= rules["old_regime"]["rebate_threshold"]:
            return money(min(normal_tax, rules["old_regime"]["rebate_max"]))
        return ZERO

    @staticmethod
    def _rebate_new(total_income: Decimal, normal_tax: Decimal, rules: dict) -> tuple[Decimal, Decimal]:
        threshold = rules["new_regime"]["rebate_threshold"]
        max_rebate = rules["new_regime"]["rebate_max"]
        if total_income <= threshold:
            return money(min(normal_tax, max_rebate)), ZERO
        excess = total_income - threshold
        if normal_tax > excess:
            marginal_relief = normal_tax - excess
            return ZERO, money(max(ZERO, marginal_relief))
        return ZERO, ZERO

    @staticmethod
    def _line(code: str, label: str, formula: str, inputs: dict, result: Decimal, *rule_ids: str) -> CalculationLine:
        safe_inputs = {key: money(value) if isinstance(value, Decimal) else value for key, value in inputs.items()}
        return CalculationLine(code=code, label=label, formula=formula, inputs=safe_inputs, result=money(result), rule_ids=list(rule_ids))

    def compute(self, req: TaxComputeRequest) -> TaxComputationResult:
        rules = load_rule_release(self.RELEASE_ID)
        blockers: list[dict] = []
        warnings: list[dict] = []
        assumptions = [
            "House-property input is an approved net income/loss for the limited V1 scope.",
            "Capital-gain aggregates must already be classified as section 111A or 112A by an approved reviewer.",
        ]
        lines: list[CalculationLine] = []

        if req.assessment_year != rules["assessment_year"]:
            blockers.append({"code": "UNSUPPORTED_ASSESSMENT_YEAR", "message": f"Only {rules['assessment_year']} is supported by this release."})
        if req.residential_status != "RESIDENT_ORDINARILY_RESIDENT":
            blockers.append({"code": "UNSUPPORTED_RESIDENTIAL_STATUS", "message": "NRI/RNOR cases require specialist review."})
        for flag, code, message in [
            (req.has_business_income, "BUSINESS_INCOME_UNSUPPORTED", "Business/professional income is outside V1."),
            (req.has_foreign_assets, "FOREIGN_ASSET_UNSUPPORTED", "Foreign assets and Schedule FA require specialist review."),
            (req.has_foreign_income, "FOREIGN_INCOME_UNSUPPORTED", "Foreign-source income and foreign tax credit are outside V1."),
            (req.has_vda_income, "VDA_UNSUPPORTED", "Virtual digital asset income is outside V1."),
            (req.has_unlisted_shares, "UNLISTED_SHARES_UNSUPPORTED", "Unlisted securities require specialist review."),
            (req.capital_gains.property_sale_price > ZERO, "PROPERTY_GAIN_UNSUPPORTED", "Property capital gains are not computed by V1."),
        ]:
            if flag:
                blockers.append({"code": code, "message": message})

        gross_salary = max(ZERO, req.gross_salary)
        other_income = req.other_income
        house_property = req.house_property_income
        stcg = max(ZERO, req.capital_gains.stcg_equity)
        ltcg = max(ZERO, req.capital_gains.ltcg_equity)
        special_gross = stcg + ltcg

        if any(value < ZERO for value in [req.gross_salary, req.section_10_exemptions, req.deductions_80c, req.deductions_80d, req.tds_deducted]):
            blockers.append({"code": "NEGATIVE_INPUT", "message": "Negative salary, deduction or tax-credit inputs are not accepted."})

        old_std = rules["standard_deduction"]["OLD"]
        new_std = rules["standard_deduction"]["NEW"]
        old_salary = max(ZERO, gross_salary - max(ZERO, req.section_10_exemptions) - old_std - max(ZERO, req.professional_tax))
        new_salary = max(ZERO, gross_salary - new_std)
        lines.append(self._line("SALARY_OLD", "Income from salary - old regime", "gross - section10 - standard deduction - professional tax", {
            "gross_salary": gross_salary,
            "section_10_exemptions": max(ZERO, req.section_10_exemptions),
            "standard_deduction": old_std,
            "professional_tax": max(ZERO, req.professional_tax),
        }, old_salary, "SALARY_OLD_V1"))
        lines.append(self._line("SALARY_NEW", "Income from salary - new regime", "gross - standard deduction", {
            "gross_salary": gross_salary,
            "standard_deduction": new_std,
        }, new_salary, "SALARY_NEW_V1"))

        normal_gti_old = max(ZERO, old_salary + house_property + other_income)
        normal_gti_new = max(ZERO, new_salary + house_property + other_income)
        cap80c = min(max(ZERO, req.deductions_80c), rules["deduction_caps"]["80C"])
        cap80d = min(max(ZERO, req.deductions_80d), rules["deduction_caps"]["80D_LIMITED_SCOPE"])
        other_deductions = max(ZERO, req.other_deductions)
        total_ded_old = min(normal_gti_old, cap80c + cap80d + other_deductions)
        normal_taxable_old = max(ZERO, normal_gti_old - total_ded_old)
        normal_taxable_new = normal_gti_new
        lines.append(self._line("DEDUCTIONS_OLD", "Chapter VI-A deductions - old regime", "limited to normal-rate gross total income", {
            "80c": cap80c, "80d": cap80d, "other": other_deductions, "normal_gti": normal_gti_old,
        }, total_ded_old, "CHAPTER_VIA_LIMIT_V1"))

        taxable_112a = max(ZERO, ltcg - rules["special_rates"]["112A_EXEMPTION"])
        stcg_tax = money(stcg * rules["special_rates"]["111A"])
        ltcg_tax = money(taxable_112a * rules["special_rates"]["112A"])
        special_tax = stcg_tax + ltcg_tax
        lines.append(self._line("TAX_111A", "Tax on section 111A gains", "section 111A taxable gain × 20%", {"gain": stcg}, stcg_tax, "RATE_111A_AY2026_27"))
        lines.append(self._line("TAX_112A", "Tax on section 112A gains", "max(gain - 125000, 0) × 12.5%", {"gain": ltcg, "exemption": rules["special_rates"]["112A_EXEMPTION"]}, ltcg_tax, "RATE_112A_AY2026_27"))

        total_income_old = normal_taxable_old + special_gross
        total_income_new = normal_taxable_new + special_gross
        if max(total_income_old, total_income_new) > rules["scope"]["max_total_income"]:
            blockers.append({"code": "SURCHARGE_SCOPE_EXCEEDED", "message": "Total income above ₹50 lakh is outside V1 because surcharge and marginal-relief review is required."})

        normal_tax_old, slabs_old = self._slab_tax(normal_taxable_old, rules["old_regime"]["slabs"])
        normal_tax_new, slabs_new = self._slab_tax(normal_taxable_new, rules["new_regime"]["slabs"])
        rebate_old = self._rebate_old(total_income_old, normal_tax_old, special_tax, rules)
        rebate_new, marginal_new = self._rebate_new(total_income_new, normal_tax_new, rules)
        tax_after_rebate_old = max(ZERO, normal_tax_old - rebate_old) + special_tax
        tax_after_rebate_new = max(ZERO, normal_tax_new - rebate_new - marginal_new) + special_tax

        if special_gross > ZERO and (total_income_old <= D("500000") or total_income_new <= D("1275000")):
            warnings.append({
                "code": "SPECIAL_RATE_REBATE_REVIEW",
                "message": "Special-rate income is present near a section 87A threshold. The conservative engine excludes special-rate tax from rebate and requires CA review.",
            })

        cess_old = money(tax_after_rebate_old * rules["cess_rate"])
        cess_new = money(tax_after_rebate_new * rules["cess_rate"])
        gross_tax_old = money(tax_after_rebate_old + cess_old)
        gross_tax_new = money(tax_after_rebate_new + cess_new)
        final_old = round_288b(gross_tax_old)
        final_new = round_288b(gross_tax_new)
        credits = money(max(ZERO, req.tds_deducted) + max(ZERO, req.tcs_collected) + max(ZERO, req.advance_tax) + max(ZERO, req.self_assessment_tax))
        payable_old = round_288b(max(ZERO, final_old - credits))
        payable_new = round_288b(max(ZERO, final_new - credits))
        refund_old = round_288b(max(ZERO, credits - final_old))
        refund_new = round_288b(max(ZERO, credits - final_new))

        lines.extend([
            self._line("REBATE_OLD", "Section 87A rebate - old regime", "eligible normal-rate tax capped at 12500", {"total_income": total_income_old, "normal_tax": normal_tax_old}, rebate_old, "87A_OLD_AY2026_27"),
            self._line("REBATE_NEW", "Section 87A rebate - new regime", "eligible normal-rate tax capped at 60000", {"total_income": total_income_new, "normal_tax": normal_tax_new}, rebate_new, "87A_NEW_AY2026_27"),
            self._line("MR_87A_NEW", "Section 87A marginal relief - new regime", "normal tax less income exceeding 1200000", {"total_income": total_income_new, "normal_tax": normal_tax_new}, marginal_new, "87A_MARGINAL_RELIEF_AY2026_27"),
            self._line("CESS_OLD", "Health and education cess - old regime", "tax after rebate × 4%", {"tax_after_rebate": tax_after_rebate_old}, cess_old, "CESS_4_PERCENT"),
            self._line("CESS_NEW", "Health and education cess - new regime", "tax after rebate × 4%", {"tax_after_rebate": tax_after_rebate_new}, cess_new, "CESS_4_PERCENT"),
            self._line("TAX_CREDITS", "Tax payments and credits", "TDS + TCS + advance tax + self-assessment tax", {"tds": max(ZERO, req.tds_deducted), "tcs": max(ZERO, req.tcs_collected), "advance_tax": max(ZERO, req.advance_tax), "self_assessment_tax": max(ZERO, req.self_assessment_tax)}, credits, "TAX_CREDITS_V1"),
        ])

        status = "BLOCKED" if blockers else ("PROVISIONAL" if warnings else "COMPLETE")
        recommended = "NEW" if final_new <= final_old else "OLD"
        input_hash = sha256_json(req)
        result_payload = {
            "status": status,
            "old": format(final_old, "f"),
            "new": format(final_new, "f"),
            "rule": rules["rule_bundle_hash"],
            "input": input_hash,
            "lines": [line.model_dump(mode="json") for line in lines],
        }
        result_hash = sha256_json(result_payload)

        return TaxComputationResult(
            computation_status=status,
            assessment_year=req.assessment_year,
            rule_release_id=rules["release_id"],
            rule_bundle_hash=rules["rule_bundle_hash"],
            input_hash=input_hash,
            result_hash=result_hash,
            blockers=blockers,
            warnings=warnings,
            assumptions=assumptions,
            calculation_lines=lines,
            facts_used=[],
            facts_not_used=[],
            gross_salary=money(gross_salary),
            taxable_income_old=money(normal_taxable_old),
            taxable_income_new=money(normal_taxable_new),
            total_income_old=money(total_income_old),
            total_income_new=money(total_income_new),
            base_tax_old=money(normal_tax_old),
            base_tax_new=money(normal_tax_new),
            rebate_old=money(rebate_old),
            rebate_new=money(rebate_new),
            marginal_relief_87a_new=money(marginal_new),
            stcg_tax=money(stcg_tax),
            ltcg_tax=money(ltcg_tax),
            property_gains=ZERO,
            cess_old=cess_old,
            cess_new=cess_new,
            tax_liability_old=money(final_old),
            tax_liability_new=money(final_new),
            gross_tax_liability_old=gross_tax_old,
            gross_tax_liability_new=gross_tax_new,
            total_tax_credits=credits,
            amount_payable_old=payable_old,
            amount_payable_new=payable_new,
            refund_old=refund_old,
            refund_new=refund_new,
            total_deductions_old=money(total_ded_old),
            savings_with_recommended=money(abs(final_old - final_new)),
            recommended_regime=recommended,
            slabs_old=slabs_old,
            slabs_new=slabs_new,
        )


engine = DeterministicTaxEngine()
