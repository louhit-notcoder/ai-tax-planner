from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ZERO = Decimal("0")


def D(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money(value: Decimal) -> Decimal:
    return D(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Regime(str, Enum):
    OLD = "OLD"
    NEW = "NEW"


class ResidentialStatus(str, Enum):
    ROR = "RESIDENT_ORDINARILY_RESIDENT"
    RNOR = "RESIDENT_NOT_ORDINARILY_RESIDENT"
    NRI = "NON_RESIDENT"


class ComputationStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PROVISIONAL = "PROVISIONAL"
    BLOCKED = "BLOCKED"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"


class AssetType(str, Enum):
    LISTED_EQUITY = "LISTED_EQUITY"
    EQUITY_MUTUAL_FUND = "EQUITY_MUTUAL_FUND"
    DEBT_MUTUAL_FUND = "DEBT_MUTUAL_FUND"
    OTHER_MUTUAL_FUND = "OTHER_MUTUAL_FUND"
    LISTED_BOND = "LISTED_BOND"
    UNLISTED_SHARE = "UNLISTED_SHARE"
    LAND_BUILDING = "LAND_BUILDING"
    GOLD = "GOLD"
    OTHER = "OTHER"


class MoneyAmount(StrictModel):
    amount: Decimal = ZERO
    currency: str = "INR"

    @field_validator("amount")
    @classmethod
    def finite_amount(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Amount must be finite")
        return money(value)


class TaxpayerProfile(StrictModel):
    taxpayer_category: Literal["INDIVIDUAL"] = "INDIVIDUAL"
    date_of_birth: date | None = None
    residential_status: ResidentialStatus = ResidentialStatus.ROR
    is_director: bool = False
    held_unlisted_equity: bool = False
    has_foreign_assets: bool = False
    has_foreign_income: bool = False
    has_signing_authority_abroad: bool = False
    has_brought_forward_losses: bool = False
    has_agricultural_income: bool = False
    opted_out_of_new_regime: bool = False


class SalaryComponent(StrictModel):
    code: str
    label: str
    amount: Decimal
    exempt_under_section_10: Decimal = ZERO
    evidence_fact_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def exemption_not_above_component(self):
        if self.amount < ZERO or self.exempt_under_section_10 < ZERO:
            raise ValueError("Salary amounts cannot be negative")
        if self.exempt_under_section_10 > self.amount:
            raise ValueError("Salary exemption cannot exceed component")
        return self


class EmploymentIncome(StrictModel):
    employment_id: str
    employer_name: str
    employer_tan: str | None = None
    employment_start: date | None = None
    employment_end: date | None = None
    components: list[SalaryComponent] = Field(default_factory=list)
    professional_tax: Decimal = ZERO
    employer_tds: Decimal = ZERO
    is_pension: bool = False
    is_family_pension: bool = False
    evidence_fact_ids: list[str] = Field(default_factory=list)

    @field_validator("professional_tax", "employer_tds")
    @classmethod
    def non_negative(cls, value: Decimal) -> Decimal:
        if value < ZERO:
            raise ValueError("Amount cannot be negative")
        return money(value)

    @property
    def gross_salary(self) -> Decimal:
        return money(sum((item.amount for item in self.components), ZERO))

    @property
    def section_10_exemptions(self) -> Decimal:
        return money(sum((item.exempt_under_section_10 for item in self.components), ZERO))


class HouseProperty(StrictModel):
    property_id: str
    address_summary: str | None = None
    ownership_percentage: Decimal = Decimal("100")
    occupancy_type: Literal["SELF_OCCUPIED", "LET_OUT", "DEEMED_LET_OUT", "PART_YEAR_LET_OUT"]
    gross_annual_value: Decimal = ZERO
    municipal_taxes_paid: Decimal = ZERO
    unrealised_rent: Decimal = ZERO
    interest_on_borrowed_capital: Decimal = ZERO
    pre_construction_interest_installment: Decimal = ZERO
    co_owner_share_income_override: Decimal | None = None
    evidence_fact_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_values(self):
        if self.ownership_percentage <= ZERO or self.ownership_percentage > Decimal("100"):
            raise ValueError("Ownership percentage must be greater than 0 and at most 100")
        for name in [
            "gross_annual_value", "municipal_taxes_paid", "unrealised_rent",
            "interest_on_borrowed_capital", "pre_construction_interest_installment",
        ]:
            if getattr(self, name) < ZERO:
                raise ValueError(f"{name} cannot be negative")
        return self


class CapitalGainTransaction(StrictModel):
    transaction_id: str
    asset_type: AssetType
    description: str | None = None
    acquisition_date: date
    transfer_date: date
    sale_consideration: Decimal
    transfer_expenses: Decimal = ZERO
    actual_cost: Decimal
    improvement_cost: Decimal = ZERO
    fmv_2018_01_31: Decimal | None = None
    value_on_2018_01_31: Decimal | None = None
    indexed_cost_override: Decimal | None = None
    stt_paid_on_acquisition: bool | None = None
    stt_paid_on_transfer: bool | None = None
    listed: bool | None = None
    acquired_before_2023_04_01: bool | None = None
    resident_individual_property_legacy_option: bool = False
    evidence_fact_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_transaction(self):
        if self.transfer_date < self.acquisition_date:
            raise ValueError("Transfer date cannot be before acquisition date")
        for name in ["sale_consideration", "transfer_expenses", "actual_cost", "improvement_cost"]:
            if getattr(self, name) < ZERO:
                raise ValueError(f"{name} cannot be negative")
        return self


class BusinessActivity(StrictModel):
    activity_id: str
    type: Literal["NORMAL", "PRESUMPTIVE_44AD", "PRESUMPTIVE_44ADA", "F_AND_O"]
    description: str | None = None
    gross_receipts: Decimal = ZERO
    digital_receipts: Decimal = ZERO
    cash_receipts: Decimal = ZERO
    net_profit_declared: Decimal = ZERO
    expenses: Decimal = ZERO
    is_eligible_profession: bool = False
    opted_presumptive: bool = False
    evidence_fact_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_amounts(self):
        for name in ["gross_receipts", "digital_receipts", "cash_receipts", "expenses"]:
            if getattr(self, name) < ZERO:
                raise ValueError(f"{name} cannot be negative")
        return self


class VDATransaction(StrictModel):
    transaction_id: str
    transfer_date: date
    sale_consideration: Decimal
    acquisition_cost: Decimal
    tds_194s: Decimal = ZERO
    evidence_fact_ids: list[str] = Field(default_factory=list)


class OtherIncome(StrictModel):
    savings_interest: Decimal = ZERO
    deposit_interest: Decimal = ZERO
    dividends: Decimal = ZERO
    family_pension: Decimal = ZERO
    lottery_income: Decimal = ZERO
    gifts_taxable: Decimal = ZERO
    other_normal_income: Decimal = ZERO
    evidence_fact_ids: list[str] = Field(default_factory=list)


class DeductionClaims(StrictModel):
    section_80c: Decimal = ZERO
    section_80ccd1b: Decimal = ZERO
    section_80d_self_family: Decimal = ZERO
    section_80d_parents: Decimal = ZERO
    self_family_has_senior: bool = False
    parents_have_senior: bool = False
    preventive_health_checkup: Decimal = ZERO
    section_80e: Decimal = ZERO
    section_80ee: Decimal = ZERO
    section_80eea: Decimal = ZERO
    section_80gga: Decimal = ZERO
    section_80gg: Decimal = ZERO
    section_80tta: Decimal = ZERO
    section_80ttb: Decimal = ZERO
    taxpayer_is_senior: bool = False
    section_80ddb: Decimal = ZERO
    specified_disease_senior: bool = False
    section_80u_severity: Literal["NONE", "NORMAL", "SEVERE"] = "NONE"
    section_80dd_severity: Literal["NONE", "NORMAL", "SEVERE"] = "NONE"
    section_80g_eligible: Decimal = ZERO
    employer_nps_80ccd2: Decimal = ZERO
    other_old_regime_deductions: Decimal = ZERO
    allowed_new_regime_deductions: Decimal = ZERO
    evidence_fact_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def non_negative_claims(self):
        for name, value in self.__dict__.items():
            if isinstance(value, Decimal) and value < ZERO:
                raise ValueError(f"{name} cannot be negative")
        return self


class TaxPayment(StrictModel):
    payment_id: str
    payment_type: Literal["TDS", "TCS", "ADVANCE_TAX", "SELF_ASSESSMENT_TAX"]
    amount: Decimal
    payment_date: date | None = None
    deductor_tan: str | None = None
    challan_serial: str | None = None
    evidence_fact_ids: list[str] = Field(default_factory=list)


class ForeignIncomeItem(StrictModel):
    item_id: str
    country_code: str
    income_type: str
    gross_income_inr: Decimal
    foreign_tax_paid_inr: Decimal = ZERO
    indian_tax_attributable_inr: Decimal | None = None
    dtaa_article: str | None = None
    dtaa_rate: Decimal | None = None
    form_67_filed: bool = False
    evidence_fact_ids: list[str] = Field(default_factory=list)


class ForeignAsset(StrictModel):
    asset_id: str
    schedule_fa_table: str
    country_code: str
    institution_or_entity: str
    address: str | None = None
    account_number_masked: str | None = None
    peak_value_inr: Decimal | None = None
    closing_value_inr: Decimal | None = None
    income_derived_inr: Decimal = ZERO
    ownership_type: str | None = None
    opening_date: date | None = None
    closing_date: date | None = None
    evidence_fact_ids: list[str] = Field(default_factory=list)


class FilingContext(StrictModel):
    original_due_date: date | None = None
    return_filing_date: date | None = None
    assessment_completion_date: date | None = None
    advance_tax_instalments_paid: dict[str, Decimal] = Field(default_factory=dict)


class TaxFactSnapshot(StrictModel):
    snapshot_id: str
    case_id: str
    assessment_year: str = "AY 2026-27"
    financial_year: str = "FY 2025-26"
    act_namespace: Literal["ITA_1961", "ITA_2025"] = "ITA_1961"
    selected_regime: Regime = Regime.NEW
    profile: TaxpayerProfile = Field(default_factory=TaxpayerProfile)
    employments: list[EmploymentIncome] = Field(default_factory=list)
    house_properties: list[HouseProperty] = Field(default_factory=list)
    capital_transactions: list[CapitalGainTransaction] = Field(default_factory=list)
    business_activities: list[BusinessActivity] = Field(default_factory=list)
    vda_transactions: list[VDATransaction] = Field(default_factory=list)
    other_income: OtherIncome = Field(default_factory=OtherIncome)
    deductions: DeductionClaims = Field(default_factory=DeductionClaims)
    tax_payments: list[TaxPayment] = Field(default_factory=list)
    foreign_income: list[ForeignIncomeItem] = Field(default_factory=list)
    foreign_assets: list[ForeignAsset] = Field(default_factory=list)
    filing: FilingContext = Field(default_factory=FilingContext)
    approved_fact_ids: list[str] = Field(default_factory=list)
    snapshot_hash: str | None = None


class CalculationLine(StrictModel):
    line_id: str
    code: str
    label: str
    formula: str
    input_line_ids: list[str] = Field(default_factory=list)
    input_fact_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    amount_before: Decimal | None = None
    adjustment: Decimal | None = None
    result: Decimal
    metadata: dict = Field(default_factory=dict)


class TaxBucket(StrictModel):
    code: str
    gross_amount: Decimal = ZERO
    current_year_loss_setoff: Decimal = ZERO
    brought_forward_loss_setoff: Decimal = ZERO
    exemption_amount: Decimal = ZERO
    taxable_amount: Decimal = ZERO
    source_fact_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    calculation_line_ids: list[str] = Field(default_factory=list)


class ComputationIssue(StrictModel):
    code: str
    message: str
    severity: Literal["INFO", "WARNING", "BLOCKER", "UNSUPPORTED"]
    related_fact_ids: list[str] = Field(default_factory=list)
    review_required: bool = False


class RegimeResult(StrictModel):
    regime: Regime
    gross_total_income: Decimal
    deductions: Decimal
    total_income: Decimal
    normal_rate_income: Decimal
    special_rate_income: Decimal
    income_tax_before_rebate: Decimal
    rebate_87a: Decimal
    rebate_marginal_relief: Decimal
    surcharge: Decimal
    surcharge_marginal_relief: Decimal
    cess: Decimal
    relief_90_90a_91: Decimal
    interest_234a: Decimal
    interest_234b: Decimal
    interest_234c: Decimal
    fee_234f: Decimal
    total_tax_liability: Decimal
    tax_paid: Decimal
    payable: Decimal
    refund: Decimal


class FormEligibilityResult(StrictModel):
    eligible_forms: list[str]
    recommended_form: str | None
    reasons: list[str]
    disqualifiers: list[str]
    rule_release: str


class ComputationResult(StrictModel):
    status: ComputationStatus
    case_id: str
    assessment_year: str
    selected_regime: Regime
    recommended_regime: Regime | None
    selected_result: RegimeResult | None
    old_regime: RegimeResult | None
    new_regime: RegimeResult | None
    buckets: list[TaxBucket]
    calculation_lines: list[CalculationLine]
    blockers: list[ComputationIssue]
    warnings: list[ComputationIssue]
    assumptions: list[str]
    facts_used: list[str]
    facts_not_used: list[str]
    missing_information: list[str]
    form_eligibility: FormEligibilityResult
    schedule_data: dict
    rule_release_id: str
    rule_bundle_hash: str
    fact_snapshot_hash: str
    engine_version: str
    result_hash: str
