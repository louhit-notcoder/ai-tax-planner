from __future__ import annotations


BASE_REQUIREMENTS = [
    ("TAXPAYER.PAN", "PAN", "Required for return identity and validation", "HIGH"),
    ("SALARY.GROSS.AGGREGATE", "Salary income", "Required when the case has salary income", "HIGH"),
    ("TAX_CREDIT.TDS.SALARY.AGGREGATE", "Salary TDS", "Required to calculate payable/refund accurately", "MEDIUM"),
]


async def list_missing_information(db, *, tenant_id: str, case_id: str, filing: dict) -> list[dict]:
    present = {
        row["field_code"]
        for row in await db.canonical_facts.find(
            {"tenant_id": tenant_id, "case_id": case_id, "is_current": True, "status": "APPROVED"},
            {"_id": 0, "field_code": 1},
        ).to_list(1000)
    }
    missing = []
    for field_code, label, reason, priority in BASE_REQUIREMENTS:
        # PAN can still be stored in secure_metadata during migration.
        if field_code == "TAXPAYER.PAN" and filing.get("pan_hash"):
            continue
        if field_code not in present:
            missing.append({
                "field_code": field_code,
                "label": label,
                "reason": reason,
                "priority": priority,
                "status": "MISSING",
            })
    pending = await db.candidate_facts.find(
        {"tenant_id": tenant_id, "case_id": case_id, "status": {"$in": ["PENDING_REVIEW", "CONFLICTING"]}},
        {"_id": 0, "candidate_fact_id": 1, "field_code": 1, "status": 1},
    ).to_list(1000)
    for item in pending:
        missing.append({
            "field_code": item["field_code"],
            "label": item["field_code"],
            "reason": "An extracted candidate requires CA review before it can enter the computation.",
            "priority": "HIGH" if item["status"] == "CONFLICTING" else "MEDIUM",
            "status": item["status"],
            "candidate_fact_id": item["candidate_fact_id"],
        })
    if filing.get("has_foreign_assets") or filing.get("has_foreign_income"):
        missing.append({
            "field_code": "EXPERT_REVIEW.CROSS_BORDER",
            "label": "Cross-border specialist review",
            "reason": "Foreign assets/income are outside automated V1 scope.",
            "priority": "HIGH",
            "status": "BLOCKED",
        })
    return missing
