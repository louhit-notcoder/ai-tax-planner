from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..db_models import CandidateFact, CanonicalFact, FactSnapshot
from ..security import Actor, assert_case_access, get_actor, require_permission
from ..services.facts_service import build_tax_snapshot, list_current_facts, propose_candidate, review_candidate
from .schemas import CandidateProposal, CandidateReview, SnapshotRequest

router = APIRouter(tags=["facts"])


@router.get("/cases/{case_id}/candidate-facts")
def candidates(case_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    assert_case_access(db, actor, case_id, "fact:read")
    rows = list(db.scalars(select(CandidateFact).where(CandidateFact.tenant_id == actor.tenant_id, CandidateFact.case_id == case_id).order_by(CandidateFact.created_at.desc())))
    return [{"id": row.id, "field_code": row.field_code, "value_type": row.value_type, "value": row.value_json, "evidence_claim_ids": row.evidence_claim_ids, "status": row.status, "source": row.source, "model_explanation": row.model_explanation, "review_justification": row.review_justification, "created_at": row.created_at} for row in rows]


@router.post("/cases/{case_id}/candidate-facts", status_code=201)
def create_candidate(case_id: str, payload: CandidateProposal, actor: Actor = Depends(require_permission("fact:propose")), db: Session = Depends(get_db)):
    row = propose_candidate(db, actor=actor, case_id=case_id, field_code=payload.field_code, entity_key=payload.entity_key, value_type=payload.value_type, value=payload.value, evidence_claim_ids=payload.evidence_claim_ids, idempotency_key=payload.idempotency_key, source="MANUAL", explanation=payload.model_explanation)
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/candidate-facts/{candidate_id}/review")
def review(candidate_id: str, payload: CandidateReview, actor: Actor = Depends(require_permission("review:*")), db: Session = Depends(get_db)):
    candidate, canonical = review_candidate(db, actor=actor, candidate_id=candidate_id, decision=payload.decision, justification=payload.justification, corrected_value=payload.corrected_value, entity_key=payload.entity_key)
    db.commit()
    return {"candidate_id": candidate.id, "candidate_status": candidate.status, "canonical_fact_id": canonical.id if canonical else None, "canonical_version": canonical.version if canonical else None}


@router.get("/cases/{case_id}/facts")
def canonical(case_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    rows = list_current_facts(db, actor, case_id)
    return [{"id": row.id, "field_code": row.field_code, "entity_key": row.entity_key, "value_type": row.value_type, "value": row.value_json, "evidence_claim_ids": row.evidence_claim_ids, "version": row.version, "approved_by": row.approved_by, "approved_at": row.approved_at} for row in rows]


@router.post("/cases/{case_id}/fact-snapshots", status_code=201)
def snapshot(case_id: str, payload: SnapshotRequest, actor: Actor = Depends(require_permission("computation:run")), db: Session = Depends(get_db)):
    record, typed = build_tax_snapshot(db, actor=actor, case_id=case_id, selected_regime=payload.selected_regime)
    db.commit()
    return {"id": record.id, "snapshot_hash": record.snapshot_hash, "facts": typed.model_dump(mode="json")}
