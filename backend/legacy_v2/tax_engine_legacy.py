"""Deterministic symbolic tax core for AY 2026-27 (FY 2025-26). Old & New regime."""
from typing import Dict
from pydantic import BaseModel


class CapitalGainsInput(BaseModel):
    stcg_equity: float = 0.0        # taxed at 20%
    ltcg_equity: float = 0.0        # taxed at 12.5% over 1.25L exemption
    property_sale_price: float = 0.0
    property_purchase_price: float = 0.0
    cii_year_purchase: int = 100
    cii_year_sale: int = 100


class TaxComputeRequest(BaseModel):
    gross_salary: float = 0.0
    section_10_exemptions: float = 0.0   # HRA/LTA etc (old regime)
    deductions_80c: float = 0.0
    deductions_80d: float = 0.0
    other_deductions: float = 0.0
    house_property_income: float = 0.0
    other_income: float = 0.0            # interest, dividend
    capital_gains: CapitalGainsInput = CapitalGainsInput()


class SlabRow(BaseModel):
    label: str
    rate: float
    taxable_amount: float
    tax: float


class TaxComputationResult(BaseModel):
    gross_salary: float
    taxable_income_old: float
    taxable_income_new: float
    base_tax_old: float
    base_tax_new: float
    stcg_tax: float
    ltcg_tax: float
    property_gains: float
    cess_old: float
    cess_new: float
    tax_liability_old: float
    tax_liability_new: float
    total_deductions_old: float
    savings_with_recommended: float
    recommended_regime: str
    slabs_old: list
    slabs_new: list


class DeterministicTaxEngine:
    STD_DEDUCTION_OLD = 50000.0
    STD_DEDUCTION_NEW = 75000.0
    CESS = 0.04

    @staticmethod
    def compute_hra_exemption(basic_salary: float, hra_received: float, rent_paid: float, is_metro: bool) -> float:
        limit_factor = 0.50 if is_metro else 0.40
        return max(0.0, min(hra_received, max(0.0, rent_paid - 0.10 * basic_salary), limit_factor * basic_salary))

    @staticmethod
    def calculate_capital_gains(cg: CapitalGainsInput) -> Dict[str, float]:
        stcg_tax = cg.stcg_equity * 0.20
        taxable_ltcg = max(0.0, cg.ltcg_equity - 125000.0)
        ltcg_tax = taxable_ltcg * 0.125
        if cg.property_sale_price > 0.0 and cg.cii_year_purchase > 0:
            indexed_cost = cg.property_purchase_price * (cg.cii_year_sale / cg.cii_year_purchase)
            property_gains = max(0.0, cg.property_sale_price - indexed_cost)
        else:
            property_gains = 0.0
        return {"stcg_tax": stcg_tax, "ltcg_tax": ltcg_tax, "property_gains": property_gains}

    def _slab_tax(self, income: float, slabs) -> (float, list):
        tax = 0.0
        remaining = income
        floor = 0.0
        rows = []
        for limit, rate in slabs:
            if remaining <= 0:
                break
            taxable_slice = min(remaining, limit)
            slice_tax = taxable_slice * rate
            tax += slice_tax
            top = floor + limit if limit != float("inf") else float("inf")
            label = f"{int(floor/100000)}L+" if top == float("inf") else f"{int(floor/100000)}-{int(top/100000)}L"
            rows.append(SlabRow(label=label, rate=rate, taxable_amount=round(taxable_slice, 2), tax=round(slice_tax, 2)).model_dump())
            remaining -= taxable_slice
            floor = top
        return tax, rows

    def new_regime(self, taxable_income: float):
        slabs = [(400000.0, 0.00), (400000.0, 0.05), (400000.0, 0.10),
                 (400000.0, 0.15), (800000.0, 0.20), (float("inf"), 0.30)]
        tax, rows = self._slab_tax(taxable_income, slabs)
        if taxable_income <= 700000.0:
            tax = 0.0
        elif 700000.0 < taxable_income <= 727500.0:
            tax = min(tax, taxable_income - 700000.0)  # marginal relief u/s 87A
        return tax, rows

    def old_regime(self, taxable_income: float):
        slabs = [(250000.0, 0.00), (250000.0, 0.05), (500000.0, 0.20), (float("inf"), 0.30)]
        tax, rows = self._slab_tax(taxable_income, slabs)
        if taxable_income <= 500000.0:
            tax = 0.0
        return tax, rows

    def compute(self, req: TaxComputeRequest) -> TaxComputationResult:
        c80 = min(req.deductions_80c, 150000.0)   # statutory cap
        c80d = min(req.deductions_80d, 100000.0)
        total_ded_old = c80 + c80d + req.other_deductions + req.section_10_exemptions

        gross_total = req.gross_salary + req.house_property_income + req.other_income

        taxable_old = max(0.0, gross_total - total_ded_old - self.STD_DEDUCTION_OLD)
        taxable_new = max(0.0, gross_total - self.STD_DEDUCTION_NEW)

        base_old, slabs_old = self.old_regime(taxable_old)
        base_new, slabs_new = self.new_regime(taxable_new)

        cg = self.calculate_capital_gains(req.capital_gains)
        cg_tax = cg["stcg_tax"] + cg["ltcg_tax"]

        pre_cess_old = base_old + cg_tax
        pre_cess_new = base_new + cg_tax
        cess_old = pre_cess_old * self.CESS
        cess_new = pre_cess_new * self.CESS
        final_old = pre_cess_old + cess_old
        final_new = pre_cess_new + cess_new

        recommended = "NEW" if final_new <= final_old else "OLD"
        savings = abs(final_old - final_new)

        return TaxComputationResult(
            gross_salary=round(req.gross_salary, 2),
            taxable_income_old=round(taxable_old, 2),
            taxable_income_new=round(taxable_new, 2),
            base_tax_old=round(base_old, 2),
            base_tax_new=round(base_new, 2),
            stcg_tax=round(cg["stcg_tax"], 2),
            ltcg_tax=round(cg["ltcg_tax"], 2),
            property_gains=round(cg["property_gains"], 2),
            cess_old=round(cess_old, 2),
            cess_new=round(cess_new, 2),
            tax_liability_old=round(final_old, 2),
            tax_liability_new=round(final_new, 2),
            total_deductions_old=round(total_ded_old, 2),
            savings_with_recommended=round(savings, 2),
            recommended_regime=recommended,
            slabs_old=slabs_old,
            slabs_new=slabs_new,
        )


engine = DeterministicTaxEngine()
