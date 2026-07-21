from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import append_audit
from ..database import get_db
from ..db_models import Client, ConsentRecord, PrivacyRequest, ReconciliationItem
from ..security import Actor, assert_case_access, get_actor, require_permission
from .schemas import ConsentCreate, PrivacyRequestCreate, ReconciliationResolve

router = APIRouter(tags=["privacy-and-reconciliation"])


@router.post("/privacy/requests", status_code=201)
def create_privacy_request(payload: PrivacyRequestCreate, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    client = db.scalar(select(Client).where(Client.id == payload.client_id, Client.tenant_id == actor.tenant_id))
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    row = PrivacyRequest(tenant_id=actor.tenant_id, client_id=client.id, request_type=payload.request_type, requested_by=actor.user_id, due_at=datetime.now(timezone.utc) + timedelta(days=30), completion_note=payload.note)
    db.add(row); db.flush()
    append_audit(db, actor=actor, action="privacy_request.created", entity_type="privacy_request", entity_id=row.id, after={"type": row.request_type, "due_at": row.due_at})
    db.commit()
    return {"id": row.id, "status": row.status, "due_at": row.due_at}


@router.post("/privacy/consents", status_code=201)
def create_consent(payload: ConsentCreate, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    client = db.scalar(select(Client).where(Client.id == payload.client_id, Client.tenant_id == actor.tenant_id))
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    row = ConsentRecord(tenant_id=actor.tenant_id, client_id=client.id, purpose_code=payload.purpose_code, notice_version=payload.notice_version, status=payload.status, captured_by=actor.user_id, evidence_json=payload.evidence, withdrawn_at=datetime.now(timezone.utc) if payload.status == "WITHDRAWN" else None)
    db.add(row); db.flush()
    append_audit(db, actor=actor, action="consent.recorded", entity_type="consent", entity_id=row.id, after={"purpose": row.purpose_code, "status": row.status, "notice_version": row.notice_version})
    db.commit()
    return {"id": row.id, "status": row.status}


@router.get("/cases/{case_id}/reconciliation")
def reconciliation(case_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    assert_case_access(db, actor, case_id, "reconciliation:*")
    rows = list(db.scalars(select(ReconciliationItem).where(ReconciliationItem.tenant_id == actor.tenant_id, ReconciliationItem.case_id == case_id)))
    return [{"id": row.id, "category": row.category, "entity_key": row.entity_key, "source_values": row.source_values, "accepted_fact_id": row.accepted_fact_id, "status": row.status, "difference_amount": str(row.difference_amount) if row.difference_amount is not None else None, "resolution_note": row.resolution_note} for row in rows]


@router.post("/reconciliation/{item_id}/resolve")
def resolve_reconciliation(item_id: str, payload: ReconciliationResolve, actor: Actor = Depends(require_permission("reconciliation:*")), db: Session = Depends(get_db)):
    row = db.scalar(select(ReconciliationItem).where(ReconciliationItem.id == item_id, ReconciliationItem.tenant_id == actor.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Reconciliation item not found")
    assert_case_access(db, actor, row.case_id, "reconciliation:*")
    row.accepted_fact_id = payload.accepted_fact_id
    row.status = payload.status
    row.resolution_note = payload.resolution_note
    row.resolved_by = actor.user_id
    row.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": row.id, "status": row.status}
