from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException

from .hashing import sha256_json
from .models import CandidateFactCreate, CandidateFactReview, CandidateStatus, ReviewDecision


# Migration registry for fields currently extracted by the legacy parsers.
FIELD_REGISTRY = {
    "gross_salary": ("SALARY.GROSS.AGGREGATE", "money"),
    "section_10_exemptions": ("SALARY.SECTION_10_EXEMPTIONS.AGGREGATE", "money"),
    "professional_tax": ("SALARY.PROFESSIONAL_TAX.AGGREGATE", "money"),
    "deductions_80c": ("DEDUCTION.80C.CLAIMED", "money"),
    "deductions_80d": ("DEDUCTION.80D.CLAIMED", "money"),
    "tds_deducted": ("TAX_CREDIT.TDS.SALARY.AGGREGATE", "money"),
    "stcg_equity": ("CAPITAL_GAIN.111A.AGGREGATE", "money"),
    "ltcg_equity": ("CAPITAL_GAIN.112A.AGGREGATE", "money"),
    "other_income": ("OTHER_SOURCE.AGGREGATE", "money"),
    "house_property_income": ("HOUSE_PROPERTY.NET_INCOME.AGGREGATE", "money"),
    "employee_pan": ("TAXPAYER.PAN", "text"),
    "employer_tan": ("SALARY.EMPLOYER.TAN", "text"),
    "employer_name": ("SALARY.EMPLOYER.NAME", "text"),
}


def _money_value(value: Any) -> dict:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid monetary value")
    return {"amount": format(amount, "f"), "currency": "INR"}


async def create_extraction_claims(
    db,
    *,
    tenant_id: str,
    case_id: str,
    document: dict,
    parsed: dict,
    actor_id: str,
    parser_version: str = "legacy-adapter-2.0.0",
) -> dict:
    extraction_run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    run = {
        "extraction_run_id": extraction_run_id,
        "tenant_id": tenant_id,
        "case_id": case_id,
        "document_id": document["id"],
        "document_version": document.get("version", 1),
        "parser_version": parser_version,
        "source": parsed.get("source", "unknown"),
        "confidence": parsed.get("confidence", 0),
        "status": "COMPLETED",
        "created_by": actor_id,
        "created_at": now,
    }
    await db.extraction_runs.insert_one(run.copy())

    evidence = []
    candidates = []
    for legacy_key, (field_code, value_type) in FIELD_REGISTRY.items():
        value = parsed.get(legacy_key)
        if value in (None, "", 0, 0.0):
            continue
        evidence_claim_id = str(uuid.uuid4())
        evidence_doc = {
            "evidence_claim_id": evidence_claim_id,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "document_id": document["id"],
            "document_version": document.get("version", 1),
            "field_code": field_code,
            "page_index": None,
            "bounding_box": None,
            "original_text": None,
            "crop_storage_path": None,
            "extraction_method": parsed.get("source", "legacy_parser"),
            "parser_version": parser_version,
            "model_id": parsed.get("model_id"),
            "raw_value": value,
            "created_at": now,
        }
        await db.evidence_claims.insert_one(evidence_doc.copy())
        evidence.append(evidence_doc)

        fact_value = _money_value(value) if value_type == "money" else str(value)
        idempotency_key = sha256_json({
            "case_id": case_id,
            "document_id": document["id"],
            "version": document.get("version", 1),
            "field_code": field_code,
            "value": fact_value,
        })
        existing = await db.candidate_facts.find_one({"idempotency_key": idempotency_key}, {"_id": 0})
        if existing:
            candidates.append(existing)
            continue
        candidate = {
            "candidate_fact_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "case_id": case_id,
            "field_code": field_code,
            "value_type": value_type,
            "value": fact_value,
            "tax_period": "FY_2025_26",
            "evidence_claim_ids": [evidence_claim_id],
            "extraction_run_id": extraction_run_id,
            "model_explanation": None,
            "idempotency_key": idempotency_key,
            "status": CandidateStatus.PENDING_REVIEW.value,
            "created_by": actor_id,
            "created_at": now,
            "reviewed_by": None,
            "reviewed_at": None,
            "review_justification": None,
        }
        await db.candidate_facts.insert_one(candidate.copy())
        candidates.append(candidate)
    return {"extraction_run": run, "evidence_claims": evidence, "candidate_facts": candidates}


async def create_candidate_fact(
    db,
    *,
    tenant_id: str,
    case_id: str,
    actor_id: str,
    request: CandidateFactCreate,
) -> dict:
    existing = await db.candidate_facts.find_one(
        {"tenant_id": tenant_id, "case_id": case_id, "idempotency_key": request.idempotency_key},
        {"_id": 0},
    )
    if existing:
        return existing
    evidence_count = await db.evidence_claims.count_documents({
        "tenant_id": tenant_id,
        "case_id": case_id,
        "evidence_claim_id": {"$in": request.evidence_claim_ids},
    })
    if evidence_count != len(set(request.evidence_claim_ids)):
        raise HTTPException(status_code=400, detail="One or more evidence claims do not belong to this case")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "candidate_fact_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "case_id": case_id,
        **request.model_dump(mode="json"),
        "status": CandidateStatus.PENDING_REVIEW.value,
        "created_by": actor_id,
        "created_at": now,
        "reviewed_by": None,
        "reviewed_at": None,
        "review_justification": None,
    }
    await db.candidate_facts.insert_one(doc.copy())
    return doc


async def review_candidate_fact(
    db,
    *,
    tenant_id: str,
    case_id: str,
    candidate_fact_id: str,
    reviewer_id: str,
    request: CandidateFactReview,
) -> dict:
    candidate = await db.candidate_facts.find_one({
        "tenant_id": tenant_id,
        "case_id": case_id,
        "candidate_fact_id": candidate_fact_id,
    }, {"_id": 0})
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate fact not found")
    if candidate.get("status") not in {
        CandidateStatus.PENDING_REVIEW.value,
        CandidateStatus.CONFLICTING.value,
        CandidateStatus.VALIDATED.value,
    }:
        raise HTTPException(status_code=409, detail="Candidate fact is not reviewable")

    now = datetime.now(timezone.utc).isoformat()
    new_status = CandidateStatus.ACCEPTED.value if request.decision == ReviewDecision.ACCEPT else CandidateStatus.REJECTED.value
    await db.candidate_facts.update_one(
        {"candidate_fact_id": candidate_fact_id},
        {"$set": {
            "status": new_status,
            "reviewed_by": reviewer_id,
            "reviewed_at": now,
            "review_justification": request.justification,
        }},
    )

    if request.decision == ReviewDecision.ACCEPT:
        # Version canonical facts rather than overwriting history.
        previous = await db.canonical_facts.find_one({
            "tenant_id": tenant_id,
            "case_id": case_id,
            "field_code": candidate["field_code"],
            "is_current": True,
        }, {"_id": 0})
        version = (previous or {}).get("version", 0) + 1
        if previous:
            await db.canonical_facts.update_one(
                {"canonical_fact_id": previous["canonical_fact_id"]},
                {"$set": {"is_current": False, "superseded_at": now, "superseded_by_candidate": candidate_fact_id}},
            )
        canonical = {
            "canonical_fact_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "case_id": case_id,
            "field_code": candidate["field_code"],
            "value_type": candidate["value_type"],
            "value": candidate["value"],
            "tax_period": candidate["tax_period"],
            "source_candidate_fact_id": candidate_fact_id,
            "source_evidence_claim_ids": candidate["evidence_claim_ids"],
            "status": "APPROVED",
            "version": version,
            "is_current": True,
            "approved_by": reviewer_id,
            "approved_at": now,
        }
        await db.canonical_facts.insert_one(canonical.copy())
    return await db.candidate_facts.find_one({"candidate_fact_id": candidate_fact_id}, {"_id": 0})


async def list_current_canonical_facts(db, *, tenant_id: str, case_id: str) -> list[dict]:
    return await db.canonical_facts.find({
        "tenant_id": tenant_id,
        "case_id": case_id,
        "is_current": True,
        "status": "APPROVED",
    }, {"_id": 0}).sort("field_code", 1).to_list(1000)
