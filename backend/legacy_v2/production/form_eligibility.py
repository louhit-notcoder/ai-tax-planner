from __future__ import annotations

from decimal import Decimal


def determine_form(*, filing: dict, computation: dict | None, canonical_facts: list[dict]) -> dict:
    reasons: list[str] = []
    disqualifiers: list[str] = []
    field_codes = {f["field_code"] for f in canonical_facts}

    total_income = Decimal("0")
    if computation:
        selected = filing.get("selected_regime", "NEW")
        key = "total_income_new" if selected == "NEW" else "total_income_old"
        total_income = Decimal(str(computation.get(key, 0)))

    if filing.get("residential_status", "RESIDENT_ORDINARILY_RESIDENT") != "RESIDENT_ORDINARILY_RESIDENT":
        disqualifiers.append("ITR-1 requires an eligible resident individual; NRI/RNOR is not supported.")
    if total_income > Decimal("5000000"):
        disqualifiers.append("Total income exceeds ₹50 lakh.")
    if filing.get("has_business_income"):
        disqualifiers.append("Business or professional income is present.")
    if filing.get("has_foreign_assets") or filing.get("has_foreign_income"):
        disqualifiers.append("Foreign assets, signing authority or foreign-source income is present.")
    if filing.get("has_unlisted_shares"):
        disqualifiers.append("Unlisted equity shares are present.")
    if "CAPITAL_GAIN.111A.AGGREGATE" in field_codes:
        disqualifiers.append("Short-term capital gain is present.")
    ltcg_112a = next((f for f in canonical_facts if f["field_code"] == "CAPITAL_GAIN.112A.AGGREGATE"), None)
    if ltcg_112a:
        amount = Decimal(str((ltcg_112a.get("value") or {}).get("amount", 0)))
        if amount > Decimal("125000"):
            disqualifiers.append("Section 112A LTCG exceeds ₹1.25 lakh.")
        else:
            reasons.append("Section 112A LTCG is within the limited ITR-1 threshold.")

    if not disqualifiers:
        reasons.append("No supported-scope ITR-1 disqualifier was detected.")
        return {
            "eligible_forms": ["ITR-1", "ITR-2"],
            "recommended_form": "ITR-1",
            "reasons": reasons,
            "disqualifiers": [],
            "rule_release": "FORM_ELIGIBILITY_AY2026_27_V1",
            "status": "PROVISIONAL_REVIEW_REQUIRED",
        }
    return {
        "eligible_forms": ["ITR-2"],
        "recommended_form": "ITR-2",
        "reasons": reasons,
        "disqualifiers": disqualifiers,
        "rule_release": "FORM_ELIGIBILITY_AY2026_27_V1",
        "status": "PROVISIONAL_REVIEW_REQUIRED",
    }
