from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from .facts import list_current_canonical_facts
from .hashing import sha256_json


FIELD_TO_REQUEST = {
    "SALARY.GROSS.AGGREGATE": "gross_salary",
    "SALARY.SECTION_10_EXEMPTIONS.AGGREGATE": "section_10_exemptions",
    "SALARY.PROFESSIONAL_TAX.AGGREGATE": "professional_tax",
    "DEDUCTION.80C.CLAIMED": "deductions_80c",
    "DEDUCTION.80D.CLAIMED": "deductions_80d",
    "OTHER_SOURCE.AGGREGATE": "other_income",
    "HOUSE_PROPERTY.NET_INCOME.AGGREGATE": "house_property_income",
    "TAX_CREDIT.TDS.SALARY.AGGREGATE": "tds_deducted",
    "TAX_CREDIT.TCS.AGGREGATE": "tcs_collected",
    "TAX_PAYMENT.ADVANCE_TAX": "advance_tax",
    "TAX_PAYMENT.SELF_ASSESSMENT": "self_assessment_tax",
    "CAPITAL_GAIN.111A.AGGREGATE": "capital_gains.stcg_equity",
    "CAPITAL_GAIN.112A.AGGREGATE": "capital_gains.ltcg_equity",
}


def _extract_value(fact: dict):
    value = fact.get("value")
    if fact.get("value_type") == "money":
        return Decimal(str((value or {}).get("amount", "0")))
    return value


async def create_fact_snapshot(db, *, tenant_id: str, case_id: str, created_by: str, rule_release_id: str) -> dict:
    facts = await list_current_canonical_facts(db, tenant_id=tenant_id, case_id=case_id)
    canonical = [
        {
            "canonical_fact_id": f["canonical_fact_id"],
            "field_code": f["field_code"],
            "value_type": f["value_type"],
            "value": f["value"],
            "version": f["version"],
            "source_evidence_claim_ids": f.get("source_evidence_claim_ids", []),
        }
        for f in facts
    ]
    now = datetime.now(timezone.utc).isoformat()
    snapshot = {
        "fact_snapshot_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "case_id": case_id,
        "rule_release_id": rule_release_id,
        "facts": canonical,
        "snapshot_hash": sha256_json(canonical),
        "created_by": created_by,
        "created_at": now,
    }
    await db.fact_snapshots.insert_one(snapshot.copy())
    return snapshot


def snapshot_to_tax_request(snapshot: dict, filing: dict) -> dict:
    payload = {
        "assessment_year": filing.get("assessment_year", "AY 2026-27"),
        "residential_status": filing.get("residential_status", "RESIDENT_ORDINARILY_RESIDENT"),
        "capital_gains": {"stcg_equity": Decimal("0"), "ltcg_equity": Decimal("0")},
        "has_business_income": bool(filing.get("has_business_income")),
        "has_foreign_assets": bool(filing.get("has_foreign_assets")),
        "has_foreign_income": bool(filing.get("has_foreign_income")),
        "has_vda_income": bool(filing.get("has_vda_income")),
        "has_unlisted_shares": bool(filing.get("has_unlisted_shares")),
    }
    facts_used = []
    facts_not_used = []
    for fact in snapshot.get("facts", []):
        target = FIELD_TO_REQUEST.get(fact["field_code"])
        if not target:
            facts_not_used.append(fact["canonical_fact_id"])
            continue
        value = _extract_value(fact)
        if target.startswith("capital_gains."):
            payload["capital_gains"][target.split(".", 1)[1]] = value
        else:
            payload[target] = value
        facts_used.append(fact["canonical_fact_id"])
    return {"request": payload, "facts_used": facts_used, "facts_not_used": facts_not_used}
