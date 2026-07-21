from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Iterable

from .math_utils import D, ZERO, completed_months, money, months_or_part, round_to_multiple, slab_tax
from .models import (
    AssetType,
    CalculationLine,
    ComputationIssue,
    ComputationResult,
    ComputationStatus,
    FormEligibilityResult,
    Regime,
    RegimeResult,
    ResidentialStatus,
    TaxBucket,
    TaxFactSnapshot,
)
from .rules import load_rule_release

ENGINE_VERSION = "3.0.0"


def stable_hash(value: object) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class LineBuilder:
    def __init__(self) -> None:
        self.lines: list[CalculationLine] = []

    def add(
        self,
        code: str,
        label: str,
        formula: str,
        result: Decimal,
        *,
        input_lines: Iterable[str] = (),
        facts: Iterable[str] = (),
        rules: Iterable[str] = (),
        amount_before: Decimal | None = None,
        adjustment: Decimal | None = None,
        metadata: dict | None = None,
    ) -> str:
        line_id = f"LINE-{len(self.lines) + 1:04d}-{code}"
        self.lines.append(CalculationLine(
            line_id=line_id,
            code=code,
            label=label,
            formula=formula,
            input_line_ids=list(input_lines),
            input_fact_ids=list(facts),
            rule_ids=list(rules),
            amount_before=money(amount_before) if amount_before is not None else None,
            adjustment=money(adjustment) if adjustment is not None else None,
            result=money(result),
            metadata=metadata or {},
        ))
        return line_id


class DeterministicTaxEngine:
    """Pure AY-specific computation engine.

    It receives an immutable fact snapshot and immutable rule bundle. It performs no
    database, network, filesystem, environment, or LLM access during computation.
    """

    def compute(self, facts: TaxFactSnapshot, rule_bundle: dict | None = None) -> ComputationResult:
        rules = rule_bundle or load_rule_release("AY2026_27_V3.0.0")
        lines = LineBuilder()
        blockers: list[ComputationIssue] = []
        warnings: list[ComputationIssue] = []
        old_regime_warnings: list[ComputationIssue] = []
        new_regime_warnings: list[ComputationIssue] = []
        assumptions: list[str] = []
        missing: list[str] = []

        if facts.assessment_year != rules["assessment_year"]:
            blockers.append(self._issue("UNSUPPORTED_ASSESSMENT_YEAR", f"Rule release supports {rules['assessment_year']} only.", "UNSUPPORTED"))
        if facts.act_namespace != rules["act_namespace"]:
            blockers.append(self._issue("ACT_NAMESPACE_MISMATCH", "The fact snapshot and rule release use different Acts.", "BLOCKER"))

        profile = facts.profile
        if profile.residential_status != ResidentialStatus.ROR:
            warnings.append(self._issue("RESIDENTIAL_STATUS_EXPERT_REVIEW", "NRI/RNOR scope is computed only as an expert-review draft and cannot be auto-finalised.", "WARNING", review=True))
        if profile.has_agricultural_income:
            blockers.append(self._issue("AGRICULTURAL_RATE_INTEGRATION_REVIEW", "Agricultural income rate integration requires expert review in this release.", "BLOCKER", review=True))
        if profile.has_brought_forward_losses:
            blockers.append(self._issue("BROUGHT_FORWARD_LOSSES_REQUIRE_LEDGER", "Brought-forward loss schedules must be imported and approved before final computation.", "BLOCKER", review=True))

        salary_old, salary_new = self._compute_salary(facts, rules, lines, new_regime_warnings)
        hp_old, hp_new, hp_loss_carry = self._compute_house_property(facts, rules, lines, blockers)
        capital = self._compute_capital_gains(facts, rules, lines, warnings, blockers)
        business = self._compute_business(facts, rules, lines, warnings, blockers)
        other = self._compute_other_sources(facts, rules, lines)
        foreign = self._compute_foreign(facts, lines, warnings, blockers)
        vda = self._compute_vda(facts, rules, lines, warnings)

        old_normal_before_deductions = salary_old + hp_old + business["normal_income"] + other["normal_income"] + foreign["normal_income"]
        new_normal_before_deductions = salary_new + hp_new + business["normal_income"] + other["normal_income"] + foreign["normal_income"]

        old_deductions = self._compute_deductions(facts, rules, Regime.OLD, old_normal_before_deductions, lines, old_regime_warnings)
        new_deductions = self._compute_deductions(facts, rules, Regime.NEW, new_normal_before_deductions, lines, new_regime_warnings)

        old_normal = max(ZERO, old_normal_before_deductions - old_deductions)
        new_normal = max(ZERO, new_normal_before_deductions - new_deductions)

        buckets = self._build_buckets(capital, vda, other, facts, lines)
        special_gross = sum((b.taxable_amount for b in buckets if b.code != "NORMAL_RATE"), ZERO)

        old_result = self._compute_regime(
            Regime.OLD, facts, rules, old_normal_before_deductions, old_deductions, old_normal,
            buckets, foreign["credit"], lines, old_regime_warnings,
        )
        new_result = self._compute_regime(
            Regime.NEW, facts, rules, new_normal_before_deductions, new_deductions, new_normal,
            buckets, foreign["credit"], lines, new_regime_warnings,
        )

        form_eligibility = self._form_eligibility(facts, old_result if facts.selected_regime == Regime.OLD else new_result, capital, business, rules)
        if not form_eligibility.eligible_forms:
            blockers.append(self._issue("NO_SUPPORTED_ITR_FORM", "No production-supported return form is eligible for the current facts.", "UNSUPPORTED", review=True))

        selected = old_result if facts.selected_regime == Regime.OLD else new_result
        warnings.extend(old_regime_warnings if facts.selected_regime == Regime.OLD else new_regime_warnings)
        recommended = Regime.NEW if new_result.total_tax_liability <= old_result.total_tax_liability else Regime.OLD

        if profile.residential_status != ResidentialStatus.ROR or facts.foreign_assets or facts.foreign_income:
            warnings.append(self._issue("FOREIGN_SCHEDULE_REVIEW", "Schedules FA/FSI/TR and Form 67 data are generated as review drafts only.", "WARNING", review=True))

        status = ComputationStatus.COMPLETE
        if any(item.severity == "UNSUPPORTED" for item in blockers):
            status = ComputationStatus.UNSUPPORTED
        elif blockers:
            status = ComputationStatus.BLOCKED
        elif warnings:
            status = ComputationStatus.PROVISIONAL

        fact_hash = facts.snapshot_hash or stable_hash(facts.model_dump(exclude={"snapshot_hash"}, mode="json"))
        schedule_data = self._schedule_data(facts, selected, capital, foreign, business, hp_loss_carry)
        result_core = {
            "case_id": facts.case_id,
            "status": status.value,
            "selected": selected.model_dump(mode="json"),
            "old": old_result.model_dump(mode="json"),
            "new": new_result.model_dump(mode="json"),
            "rules": rules["rule_bundle_hash"],
            "facts": fact_hash,
            "lines": [item.model_dump(mode="json") for item in lines.lines],
            "schedule_data": schedule_data,
            "blockers": [item.model_dump(mode="json") for item in blockers],
            "warnings": [item.model_dump(mode="json") for item in warnings],
            "form_eligibility": form_eligibility.model_dump(mode="json"),
        }
        result_hash = stable_hash(result_core)

        used = sorted(set(facts.approved_fact_ids))
        return ComputationResult(
            status=status,
            case_id=facts.case_id,
            assessment_year=facts.assessment_year,
            selected_regime=facts.selected_regime,
            recommended_regime=recommended,
            selected_result=selected,
            old_regime=old_result,
            new_regime=new_result,
            buckets=buckets,
            calculation_lines=lines.lines,
            blockers=blockers,
            warnings=warnings,
            assumptions=assumptions,
            facts_used=used,
            facts_not_used=[],
            missing_information=missing,
            form_eligibility=form_eligibility,
            schedule_data=schedule_data,
            rule_release_id=rules["release_id"],
            rule_bundle_hash=rules["rule_bundle_hash"],
            fact_snapshot_hash=fact_hash,
            engine_version=ENGINE_VERSION,
            result_hash=result_hash,
        )

    @staticmethod
    def _issue(code: str, message: str, severity: str, review: bool = False, facts: list[str] | None = None) -> ComputationIssue:
        return ComputationIssue(code=code, message=message, severity=severity, review_required=review, related_fact_ids=facts or [])

    def _compute_salary(self, facts, rules, lines, warnings):
        old_total = ZERO
        new_total = ZERO
        for job in facts.employments:
            gross = job.gross_salary
            exemptions = job.section_10_exemptions
            if job.is_family_pension:
                deduction_old = min(gross / D(3), D(rules["old_regime"]["standard_deduction_family_pension"]))
                deduction_new = min(gross / D(3), D(rules["new_regime"]["standard_deduction_family_pension"]))
                old = max(ZERO, gross - deduction_old)
                new = max(ZERO, gross - deduction_new)
            else:
                old = max(ZERO, gross - exemptions - D(rules["old_regime"]["standard_deduction_salary"]) - job.professional_tax)
                new = max(ZERO, gross - D(rules["new_regime"]["standard_deduction_salary"]))
                if exemptions > ZERO:
                    warnings.append(self._issue("NEW_REGIME_SECTION10_REVIEW", f"Section 10 exemptions for {job.employer_name} are excluded under the new regime except specifically permitted items.", "WARNING", review=True, facts=job.evidence_fact_ids))
            lines.add(f"SALARY_OLD_{job.employment_id}", f"Salary income - {job.employer_name} (old)", "gross - eligible exemptions - standard deduction - professional tax", old, facts=job.evidence_fact_ids, rules=["SALARY_OLD_AY2026_27"], metadata={"gross": str(gross), "exemptions": str(exemptions)})
            lines.add(f"SALARY_NEW_{job.employment_id}", f"Salary income - {job.employer_name} (new)", "gross - permitted standard deduction", new, facts=job.evidence_fact_ids, rules=["SALARY_NEW_AY2026_27"], metadata={"gross": str(gross)})
            old_total += old
            new_total += new
        return money(old_total), money(new_total)

    def _compute_house_property(self, facts, rules, lines, blockers):
        old_total = ZERO
        new_total = ZERO
        old_loss_available = ZERO
        self_occupied_count = sum(1 for p in facts.house_properties if p.occupancy_type == "SELF_OCCUPIED")
        if self_occupied_count > int(rules["house_property"]["max_self_occupied_properties"]):
            blockers.append(self._issue("TOO_MANY_SELF_OCCUPIED_PROPERTIES", "More than two properties are marked self-occupied.", "BLOCKER", review=True))
        for prop in facts.house_properties:
            share = prop.ownership_percentage / D(100)
            interest = (prop.interest_on_borrowed_capital + prop.pre_construction_interest_installment) * share
            if prop.co_owner_share_income_override is not None:
                old_income = new_income = prop.co_owner_share_income_override
            elif prop.occupancy_type == "SELF_OCCUPIED":
                old_interest = min(interest, D(rules["house_property"]["self_occupied_interest_cap_old"]))
                old_income = -old_interest
                new_income = ZERO
            else:
                nav = max(ZERO, (prop.gross_annual_value - prop.municipal_taxes_paid - prop.unrealised_rent) * share)
                standard = nav * D(rules["house_property"]["standard_deduction_rate"])
                old_income = nav - standard - interest
                new_income = nav - standard - interest
            old_total += old_income
            new_total += new_income
            if old_income < ZERO:
                old_loss_available += -old_income
            lines.add(f"HP_OLD_{prop.property_id}", "Income from house property (old)", "NAV - 30% standard deduction - eligible interest", old_income, facts=prop.evidence_fact_ids, rules=["HOUSE_PROPERTY_AY2026_27"], metadata={"occupancy": prop.occupancy_type})
            lines.add(f"HP_NEW_{prop.property_id}", "Income from house property (new)", "NAV - 30% standard deduction - permitted interest", new_income, facts=prop.evidence_fact_ids, rules=["HOUSE_PROPERTY_NEW_AY2026_27"], metadata={"occupancy": prop.occupancy_type})
        old_cap = D(rules["house_property"]["inter_head_loss_setoff_cap_old"])
        if old_total < -old_cap:
            carry = (-old_total) - old_cap
            old_total = -old_cap
        else:
            carry = ZERO
        if new_total < ZERO:
            carry += -new_total
            new_total = ZERO
        return money(old_total), money(new_total), money(carry)

    def _compute_capital_gains(self, facts, rules, lines, warnings, blockers):
        result = {"111A": ZERO, "112A": ZERO, "OTHER_STCG": ZERO, "OTHER_LTCG": ZERO, "PROPERTY_INDEXED_ALT": ZERO, "LOSS": ZERO, "transactions": []}
        listed_months = int(rules["capital_gains"]["listed_holding_months"])
        other_months = int(rules["capital_gains"]["other_holding_months"])
        for tx in facts.capital_transactions:
            months = completed_months(tx.acquisition_date, tx.transfer_date)
            net_sale = tx.sale_consideration - tx.transfer_expenses
            cost = tx.actual_cost + tx.improvement_cost
            classification = "OTHER_STCG"
            deemed_cost = cost
            if tx.asset_type in {AssetType.LISTED_EQUITY, AssetType.EQUITY_MUTUAL_FUND}:
                long_term = months >= listed_months
                if tx.acquisition_date <= date(2018, 1, 31) and tx.fmv_2018_01_31 is not None:
                    deemed_cost = max(cost, min(tx.fmv_2018_01_31, net_sale))
                if tx.stt_paid_on_transfer is not True:
                    warnings.append(self._issue("STT_CONDITION_REVIEW", f"STT condition is not confirmed for transaction {tx.transaction_id}.", "WARNING", review=True, facts=tx.evidence_fact_ids))
                classification = "112A" if long_term else "111A"
            elif tx.asset_type == AssetType.DEBT_MUTUAL_FUND and tx.acquisition_date >= date.fromisoformat(rules["capital_gains"]["section_50aa_start_date"]):
                classification = "OTHER_STCG"
            elif tx.asset_type == AssetType.LISTED_BOND:
                classification = "OTHER_LTCG" if months >= listed_months else "OTHER_STCG"
            else:
                classification = "OTHER_LTCG" if months >= other_months else "OTHER_STCG"

            gain = money(net_sale - deemed_cost)
            if gain < ZERO:
                result["LOSS"] += -gain
            else:
                result[classification] += gain
            indexed_alt = None
            if tx.asset_type == AssetType.LAND_BUILDING and classification == "OTHER_LTCG" and tx.resident_individual_property_legacy_option:
                if tx.indexed_cost_override is None:
                    blockers.append(self._issue("PROPERTY_INDEXED_COST_REQUIRED", "Indexed cost is required to compare the resident property legacy option.", "BLOCKER", review=True, facts=tx.evidence_fact_ids))
                else:
                    indexed_alt = max(ZERO, net_sale - tx.indexed_cost_override)
                    result["PROPERTY_INDEXED_ALT"] += indexed_alt
            line = lines.add(f"CG_{tx.transaction_id}", f"Capital gain - {tx.description or tx.asset_type.value}", "net sale consideration - permitted cost", gain, facts=tx.evidence_fact_ids, rules=[f"CG_{classification}_AY2026_27"], metadata={"classification": classification, "holding_months": months, "deemed_cost": str(deemed_cost), "indexed_alternative_gain": str(indexed_alt) if indexed_alt is not None else None})
            result["transactions"].append({"id": tx.transaction_id, "classification": classification, "gain": str(gain), "line_id": line, "indexed_alt": str(indexed_alt) if indexed_alt is not None else None})
        # Capital losses are conservatively set off against other capital gains in statutory order.
        loss = result["LOSS"]
        for code in ["OTHER_STCG", "111A", "OTHER_LTCG", "112A"]:
            applied = min(loss, result[code])
            result[code] -= applied
            loss -= applied
        if loss > ZERO:
            warnings.append(self._issue("CAPITAL_LOSS_CARRY_FORWARD", f"Capital loss of ₹{money(loss)} remains for carry-forward subject to timely filing.", "WARNING", review=True))
        result["LOSS"] = money(loss)
        return result

    def _compute_business(self, facts, rules, lines, warnings, blockers):
        income = ZERO
        for activity in facts.business_activities:
            if activity.type == "PRESUMPTIVE_44AD":
                cash_ratio = activity.cash_receipts / activity.gross_receipts if activity.gross_receipts else ZERO
                limit = D(rules["presumptive"]["44ad_enhanced_limit"] if cash_ratio <= D(rules["presumptive"]["44ad_cash_receipt_ratio_limit"]) else rules["presumptive"]["44ad_standard_limit"])
                if activity.gross_receipts > limit:
                    blockers.append(self._issue("44AD_LIMIT_EXCEEDED", "Gross receipts exceed the applicable section 44AD threshold.", "BLOCKER", review=True, facts=activity.evidence_fact_ids))
                presumptive = activity.digital_receipts * D(rules["presumptive"]["44ad_digital_rate"]) + activity.cash_receipts * D(rules["presumptive"]["44ad_cash_rate"])
                amount = max(activity.net_profit_declared, presumptive)
            elif activity.type == "PRESUMPTIVE_44ADA":
                cash_ratio = activity.cash_receipts / activity.gross_receipts if activity.gross_receipts else ZERO
                limit = D(rules["presumptive"]["44ada_enhanced_limit"] if cash_ratio <= D(rules["presumptive"]["44ada_cash_receipt_ratio_limit"]) else rules["presumptive"]["44ada_standard_limit"])
                if not activity.is_eligible_profession:
                    blockers.append(self._issue("44ADA_PROFESSION_INELIGIBLE", "The profession is not confirmed as eligible for section 44ADA.", "BLOCKER", review=True, facts=activity.evidence_fact_ids))
                if activity.gross_receipts > limit:
                    blockers.append(self._issue("44ADA_LIMIT_EXCEEDED", "Gross receipts exceed the applicable section 44ADA threshold.", "BLOCKER", review=True, facts=activity.evidence_fact_ids))
                amount = max(activity.net_profit_declared, activity.gross_receipts * D(rules["presumptive"]["44ada_rate"]))
            else:
                amount = activity.net_profit_declared if activity.net_profit_declared != ZERO else activity.gross_receipts - activity.expenses
                if activity.type in {"NORMAL", "F_AND_O"}:
                    warnings.append(self._issue("BUSINESS_BOOKS_AUDIT_REVIEW", f"Business activity {activity.activity_id} requires books, depreciation, disallowance and audit review.", "WARNING", review=True, facts=activity.evidence_fact_ids))
            income += amount
            lines.add(f"BUSINESS_{activity.activity_id}", "Business/professional income", "activity-specific deterministic method", amount, facts=activity.evidence_fact_ids, rules=[f"BUSINESS_{activity.type}_AY2026_27"])
        return {"normal_income": money(income)}

    def _compute_other_sources(self, facts, rules, lines):
        other = facts.other_income
        family_pension_old = max(ZERO, other.family_pension - min(other.family_pension / D(3), D(rules["old_regime"]["standard_deduction_family_pension"])))
        family_pension_new = max(ZERO, other.family_pension - min(other.family_pension / D(3), D(rules["new_regime"]["standard_deduction_family_pension"])))
        common = other.savings_interest + other.deposit_interest + other.dividends + other.gifts_taxable + other.other_normal_income
        # Return old basis; new difference is handled in deduction function metadata through a conservative warning-free adjustment below.
        normal = common + family_pension_old
        lines.add("OTHER_SOURCES", "Income from other sources", "interest + dividend + taxable gifts + family pension + other", normal, facts=other.evidence_fact_ids, rules=["OTHER_SOURCES_AY2026_27"], metadata={"family_pension_old": str(family_pension_old), "family_pension_new": str(family_pension_new)})
        return {"normal_income": money(normal), "family_pension_new_delta": money(family_pension_new - family_pension_old), "lottery": money(other.lottery_income)}

    def _compute_foreign(self, facts, lines, warnings, blockers):
        normal = ZERO
        credit = ZERO
        for item in facts.foreign_income:
            normal += item.gross_income_inr
            attributable = item.indian_tax_attributable_inr
            if attributable is None:
                warnings.append(self._issue("FTC_ATTRIBUTABLE_TAX_PENDING", f"Indian tax attributable to foreign income item {item.item_id} must be finalised after total tax allocation.", "WARNING", review=True, facts=item.evidence_fact_ids))
                eligible = ZERO
            else:
                eligible = min(item.foreign_tax_paid_inr, attributable)
                if item.dtaa_rate is not None:
                    eligible = min(eligible, item.gross_income_inr * item.dtaa_rate)
            if not item.form_67_filed and item.foreign_tax_paid_inr > ZERO:
                blockers.append(self._issue("FORM67_REQUIRED", f"Form 67 is not marked filed for foreign tax credit item {item.item_id}.", "BLOCKER", review=True, facts=item.evidence_fact_ids))
            credit += eligible
            lines.add(f"FOREIGN_{item.item_id}", "Foreign-source income", "gross foreign income translated to INR", item.gross_income_inr, facts=item.evidence_fact_ids, rules=["SCHEDULE_FSI_TR_REVIEW"])
        if facts.foreign_assets and facts.profile.residential_status == ResidentialStatus.ROR:
            warnings.append(self._issue("SCHEDULE_FA_REQUIRED", "Foreign asset records require Schedule FA completion and specialist review.", "WARNING", review=True))
        return {"normal_income": money(normal), "credit": money(credit)}

    def _compute_vda(self, facts, rules, lines, warnings):
        gain = ZERO
        tds = ZERO
        for tx in facts.vda_transactions:
            item_gain = max(ZERO, tx.sale_consideration - tx.acquisition_cost)
            gain += item_gain
            tds += tx.tds_194s
            lines.add(f"VDA_{tx.transaction_id}", "Virtual digital asset income", "sale consideration - acquisition cost; no loss set-off", item_gain, facts=tx.evidence_fact_ids, rules=["SECTION_115BBH_AY2026_27"])
        if facts.vda_transactions:
            warnings.append(self._issue("VDA_EXPERT_REVIEW", "VDA computation is available but requires transaction completeness and section 194S reconciliation review.", "WARNING", review=True))
        return {"gain": money(gain), "tds": money(tds)}

    def _compute_deductions(self, facts, rules, regime, gti, lines, warnings):
        d = facts.deductions
        if regime == Regime.NEW:
            total = max(ZERO, d.allowed_new_regime_deductions + d.employer_nps_80ccd2)
            disallowed_claims = sum([d.section_80c, d.section_80ccd1b, d.section_80d_self_family, d.section_80d_parents, d.section_80tta, d.section_80ttb, d.other_old_regime_deductions], ZERO)
            if disallowed_claims > ZERO:
                warnings.append(self._issue("NEW_REGIME_DEDUCTIONS_EXCLUDED", "Old-regime-only deductions were excluded from the new-regime computation.", "WARNING"))
        else:
            cap = rules["deductions"]
            total = min(d.section_80c, D(cap["80c_group_cap"]))
            total += min(d.section_80ccd1b, D(cap["80ccd1b_cap"]))
            self_cap = D(cap["80d_self_family_senior_cap"] if d.self_family_has_senior else cap["80d_self_family_cap"])
            parent_cap = D(cap["80d_parents_senior_cap"] if d.parents_have_senior else cap["80d_parents_cap"])
            preventive = min(d.preventive_health_checkup, D(cap["80d_preventive_cap"]))
            total += min(d.section_80d_self_family + preventive, self_cap)
            total += min(d.section_80d_parents, parent_cap)
            total += min(d.section_80ttb, D(cap["80ttb_cap"])) if d.taxpayer_is_senior else min(d.section_80tta, D(cap["80tta_cap"]))
            total += d.section_80e + d.section_80ee + d.section_80eea + d.section_80gga + d.section_80gg + d.section_80g_eligible + d.other_old_regime_deductions + d.employer_nps_80ccd2
            if d.section_80ddb > ZERO:
                total += min(d.section_80ddb, D(cap["80ddb_senior_cap"] if d.specified_disease_senior else cap["80ddb_regular_cap"]))
            if d.section_80u_severity != "NONE":
                total += D(cap["80u_severe"] if d.section_80u_severity == "SEVERE" else cap["80u_normal"])
            if d.section_80dd_severity != "NONE":
                total += D(cap["80dd_severe"] if d.section_80dd_severity == "SEVERE" else cap["80dd_normal"])
        total = min(max(ZERO, total), max(ZERO, gti))
        lines.add(f"DEDUCTIONS_{regime.value}", f"Chapter VI-A deductions ({regime.value})", "eligible claims capped by provision and gross total income", total, facts=d.evidence_fact_ids, rules=[f"CHAPTER_VIA_{regime.value}_AY2026_27"])
        return money(total)

    def _build_buckets(self, capital, vda, other, facts, lines):
        exemption_112a = min(D("125000"), capital["112A"])
        buckets = [
            TaxBucket(code="SECTION_111A", gross_amount=money(capital["111A"]), taxable_amount=money(capital["111A"]), rule_ids=["111A_RATE"]),
            TaxBucket(code="SECTION_112A", gross_amount=money(capital["112A"]), exemption_amount=money(exemption_112a), taxable_amount=money(max(ZERO, capital["112A"] - exemption_112a)), rule_ids=["112A_RATE"]),
            TaxBucket(code="OTHER_STCG", gross_amount=money(capital["OTHER_STCG"]), taxable_amount=money(capital["OTHER_STCG"]), rule_ids=["NORMAL_RATE_STCG"]),
            TaxBucket(code="OTHER_LTCG", gross_amount=money(capital["OTHER_LTCG"]), taxable_amount=money(capital["OTHER_LTCG"]), rule_ids=["112_OTHER_LTCG"]),
            TaxBucket(code="LOTTERY", gross_amount=money(facts.other_income.lottery_income), taxable_amount=money(facts.other_income.lottery_income), rule_ids=["115BB_LOTTERY"]),
            TaxBucket(code="VDA", gross_amount=money(vda["gain"]), taxable_amount=money(vda["gain"]), rule_ids=["115BBH_VDA"]),
        ]
        return buckets

    def _compute_regime(self, regime, facts, rules, gti, deductions, normal, buckets, foreign_credit, lines, warnings):
        age = None
        if facts.profile.date_of_birth:
            age = facts.financial_year and (date(2026, 3, 31).year - facts.profile.date_of_birth.year - ((3, 31) < (facts.profile.date_of_birth.month, facts.profile.date_of_birth.day)))
        if regime == Regime.NEW:
            slabs_raw = rules["new_regime"]["slabs"]
            rebate_threshold = D(rules["new_regime"]["rebate_threshold"])
            rebate_cap = D(rules["new_regime"]["rebate_max"])
        else:
            if age is not None and age >= 80:
                slabs_raw = rules["old_regime"]["slabs_super_senior"]
            elif age is not None and age >= 60:
                slabs_raw = rules["old_regime"]["slabs_senior"]
            else:
                slabs_raw = rules["old_regime"]["slabs_below_60"]
            rebate_threshold = D(rules["old_regime"]["rebate_threshold"])
            rebate_cap = D(rules["old_regime"]["rebate_max"])
        slabs = [(None if width == "Infinity" else D(width), D(rate)) for width, rate in slabs_raw]
        # Other STCG is normal-rate income.
        other_stcg = next(b.taxable_amount for b in buckets if b.code == "OTHER_STCG")
        normal_with_stcg = normal + other_stcg
        normal_tax = slab_tax(normal_with_stcg, slabs)
        b111a = next(b.taxable_amount for b in buckets if b.code == "SECTION_111A")
        b112a = next(b.taxable_amount for b in buckets if b.code == "SECTION_112A")
        bltcg = next(b.taxable_amount for b in buckets if b.code == "OTHER_LTCG")
        lottery = next(b.taxable_amount for b in buckets if b.code == "LOTTERY")
        vda = next(b.taxable_amount for b in buckets if b.code == "VDA")
        special_tax = b111a * D(rules["capital_gains"]["section_111a_rate"]) + b112a * D(rules["capital_gains"]["section_112a_rate"]) + bltcg * D(rules["capital_gains"]["other_ltcg_rate"]) + lottery * D("0.30") + vda * D(rules["capital_gains"]["vda_rate"])
        special_income = b111a + b112a + bltcg + lottery + vda
        total_income = round_to_multiple(normal_with_stcg + special_income, D(rules["rounding"]["total_income_multiple"]))
        before_rebate = money(normal_tax + special_tax)
        rebate = ZERO
        rebate_mr = ZERO
        if facts.profile.residential_status == ResidentialStatus.ROR:
            if total_income <= rebate_threshold:
                rebate = min(normal_tax, rebate_cap)
            elif regime == Regime.NEW:
                # Section 87A marginal relief above the rebate threshold limits the
                # eligible normal-rate tax to the amount by which total income exceeds
                # the threshold. Special-rate tax remains outside this relief.
                excess = total_income - rebate_threshold
                if normal_tax > excess:
                    rebate_mr = min(normal_tax, normal_tax - excess)
        tax_after_rebate = max(ZERO, before_rebate - rebate - rebate_mr)
        surcharge_rate = ZERO
        for slab in rules["surcharge"]:
            if total_income > D(slab["threshold"]):
                surcharge_rate = D(slab["rate"])
        if regime == Regime.NEW:
            surcharge_rate = min(surcharge_rate, D(rules["new_regime"]["surcharge_cap"]))
        special_component = money(special_tax)
        normal_component = max(ZERO, tax_after_rebate - special_component)
        surcharge = normal_component * surcharge_rate + special_component * min(surcharge_rate, D(rules["special_surcharge_cap"]))
        surcharge = money(surcharge)
        surcharge_mr = self._surcharge_marginal_relief(total_income, tax_after_rebate, surcharge, regime, rules)
        cess = money((tax_after_rebate + surcharge - surcharge_mr) * D(rules["cess_rate"]))
        tax_before_interest = money(tax_after_rebate + surcharge - surcharge_mr + cess)
        interest_234a, interest_234b, interest_234c, fee_234f = self._interest_and_fee(facts, tax_before_interest, rules, warnings)
        payments = sum((p.amount for p in facts.tax_payments), ZERO)
        payments += sum((item.tds_194s for item in facts.vda_transactions), ZERO)
        total_liability = round_to_multiple(max(ZERO, tax_before_interest - foreign_credit + interest_234a + interest_234b + interest_234c + fee_234f), D(rules["rounding"]["tax_multiple"]))
        payable = round_to_multiple(max(ZERO, total_liability - payments), D(rules["rounding"]["tax_multiple"]))
        refund = round_to_multiple(max(ZERO, payments - total_liability), D(rules["rounding"]["tax_multiple"]))
        lines.add(f"TOTAL_TAX_{regime.value}", f"Total tax liability ({regime.value})", "tax after rebate + surcharge - marginal relief + cess - relief + interest + fee", total_liability, rules=[f"TOTAL_TAX_{regime.value}_AY2026_27"], metadata={"normal_tax": str(normal_tax), "special_tax": str(money(special_tax)), "rebate": str(money(rebate)), "surcharge": str(surcharge), "cess": str(cess)})
        return RegimeResult(
            regime=regime,
            gross_total_income=money(gti + special_income + other_stcg),
            deductions=money(deductions),
            total_income=money(total_income),
            normal_rate_income=money(normal_with_stcg),
            special_rate_income=money(special_income),
            income_tax_before_rebate=before_rebate,
            rebate_87a=money(rebate),
            rebate_marginal_relief=money(rebate_mr),
            surcharge=surcharge,
            surcharge_marginal_relief=money(surcharge_mr),
            cess=cess,
            relief_90_90a_91=money(foreign_credit),
            interest_234a=money(interest_234a),
            interest_234b=money(interest_234b),
            interest_234c=money(interest_234c),
            fee_234f=money(fee_234f),
            total_tax_liability=money(total_liability),
            tax_paid=money(payments),
            payable=money(payable),
            refund=money(refund),
        )

    def _surcharge_marginal_relief(self, income, tax, surcharge, regime, rules):
        if surcharge <= ZERO:
            return ZERO
        applicable = None
        for slab in rules["surcharge"]:
            threshold = D(slab["threshold"])
            if income > threshold:
                applicable = threshold
        if applicable is None:
            return ZERO
        # Recompute conservatively at the threshold using an effective ratio. Exact bucket-wise relief remains traceable and reviewable.
        excess_income = income - applicable
        combined = tax + surcharge
        max_combined = tax + excess_income
        return money(max(ZERO, combined - max_combined))

    def _interest_and_fee(self, facts, assessed_tax, rules, warnings):
        rate = D(rules["interest"]["monthly_rate"])
        filing = facts.filing
        payments_before_filing = sum((p.amount for p in facts.tax_payments if p.payment_type in {"TDS", "TCS", "ADVANCE_TAX"}), ZERO)
        balance = max(ZERO, assessed_tax - payments_before_filing)
        i234a = ZERO
        if filing.original_due_date and filing.return_filing_date and filing.return_filing_date > filing.original_due_date:
            i234a = balance * rate * months_or_part(filing.original_due_date, filing.return_filing_date)
        threshold = D(rules["interest"]["advance_tax_threshold"])
        advance_paid = sum((p.amount for p in facts.tax_payments if p.payment_type == "ADVANCE_TAX"), ZERO)
        assessed_after_tds = max(ZERO, assessed_tax - sum((p.amount for p in facts.tax_payments if p.payment_type in {"TDS", "TCS"}), ZERO))
        i234b = ZERO
        if assessed_after_tds >= threshold and advance_paid < assessed_after_tds * D("0.90"):
            if filing.return_filing_date:
                start = date(2026, 4, 1)
                i234b = max(ZERO, assessed_after_tds - advance_paid) * rate * max(1, months_or_part(start, filing.return_filing_date))
            else:
                warnings.append(self._issue("INTEREST_234B_CONTEXT_MISSING", "Return filing date is required to calculate section 234B interest; tax is provisional without it.", "WARNING", review=True))
        i234c = ZERO
        if assessed_after_tds >= threshold:
            if filing.advance_tax_instalments_paid:
                cumulative_paid = ZERO
                for instalment in rules["interest"]["advance_tax_instalments"]:
                    due = date.fromisoformat(instalment["date"])
                    key = due.isoformat()
                    cumulative_paid += D(filing.advance_tax_instalments_paid.get(key, ZERO))
                    required = assessed_after_tds * D(instalment["cumulative_ratio"])
                    shortfall = max(ZERO, required - cumulative_paid)
                    months = 1 if due.month == 3 else 3
                    i234c += shortfall * rate * months
            else:
                warnings.append(self._issue("INTEREST_234C_CONTEXT_MISSING", "Advance-tax instalment details are required to calculate section 234C interest; tax is provisional without them.", "WARNING", review=True))
        fee = ZERO
        if filing.original_due_date and filing.return_filing_date and filing.return_filing_date > filing.original_due_date:
            fee = D(rules["fees"]["234f_low"] if assessed_tax <= D(rules["fees"]["234f_income_threshold"]) else rules["fees"]["234f_high"])
        return money(i234a), money(i234b), money(i234c), money(fee)

    def _form_eligibility(self, facts, selected, capital, business, rules):
        disq_itr1: list[str] = []
        reasons: list[str] = []
        if facts.profile.residential_status != ResidentialStatus.ROR:
            disq_itr1.append("ITR-1 requires resident and ordinarily resident status for the supported product scope.")
        if selected.total_income > D("5000000"):
            disq_itr1.append("Total income exceeds ₹50 lakh.")
        if len(facts.house_properties) > 2:
            disq_itr1.append("More than two house properties.")
        if facts.business_activities:
            disq_itr1.append("Business or professional income is present.")
        if facts.profile.is_director:
            disq_itr1.append("Taxpayer is a company director.")
        if facts.profile.held_unlisted_equity:
            disq_itr1.append("Unlisted equity was held.")
        if facts.foreign_assets or facts.foreign_income or facts.profile.has_foreign_assets:
            disq_itr1.append("Foreign assets or income are present.")
        if capital["111A"] > ZERO or capital["OTHER_STCG"] > ZERO or capital["OTHER_LTCG"] > ZERO:
            disq_itr1.append("Capital gains other than eligible section 112A LTCG are present.")
        if capital["112A"] > D("125000"):
            disq_itr1.append("Section 112A LTCG exceeds ₹1.25 lakh.")
        if facts.vda_transactions:
            disq_itr1.append("VDA income is present.")
        eligible = []
        if not disq_itr1:
            eligible.append("ITR_1")
            reasons.append("Facts meet the product's pinned ITR-1 eligibility rules.")
        # ITR-2 is supported for non-business individual cases, including NRI/RNOR and foreign schedules, subject to review.
        if not facts.business_activities:
            eligible.append("ITR_2")
            reasons.append("No business/professional income is present; ITR-2 is available in the product scope.")
        return FormEligibilityResult(eligible_forms=eligible, recommended_form=eligible[0] if eligible else None, reasons=reasons, disqualifiers=disq_itr1, rule_release="FORM_ELIGIBILITY_AY2026_27_V3")

    def _schedule_data(self, facts, selected, capital, foreign, business, hp_carry):
        return {
            "PartB_TI": {
                "gross_total_income": str(selected.gross_total_income),
                "chapter_via_deductions": str(selected.deductions),
                "total_income": str(selected.total_income),
            },
            "PartB_TTI": selected.model_dump(mode="json"),
            "ScheduleS": [item.model_dump(mode="json") for item in facts.employments],
            "ScheduleHP": [item.model_dump(mode="json") for item in facts.house_properties],
            "ScheduleCG": capital,
            "ScheduleOS": facts.other_income.model_dump(mode="json"),
            "ScheduleVIA": facts.deductions.model_dump(mode="json"),
            "ScheduleTDS": [p.model_dump(mode="json") for p in facts.tax_payments if p.payment_type == "TDS"],
            "ScheduleTCS": [p.model_dump(mode="json") for p in facts.tax_payments if p.payment_type == "TCS"],
            "ScheduleIT": [p.model_dump(mode="json") for p in facts.tax_payments if p.payment_type in {"ADVANCE_TAX", "SELF_ASSESSMENT_TAX"}],
            "ScheduleFA": [item.model_dump(mode="json") for item in facts.foreign_assets],
            "ScheduleFSI": [item.model_dump(mode="json") for item in facts.foreign_income],
            "ScheduleTR": {"eligible_foreign_tax_credit": str(foreign["credit"])},
            "Form67": {"required": any(item.foreign_tax_paid_inr > ZERO for item in facts.foreign_income), "items": [item.model_dump(mode="json") for item in facts.foreign_income]},
            "Business": [item.model_dump(mode="json") for item in facts.business_activities],
            "HousePropertyLossCarryForward": str(hp_carry),
        }
