from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import append_audit
from ..database import get_db
from ..db_models import AuditEvent, MissingItem
from ..security import Actor, assert_case_access, get_actor, require_permission

router = APIRouter(tags=["review-and-audit"])


@router.get("/cases/{case_id}/missing-items")
def list_missing_items(case_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    assert_case_access(db, actor, case_id, "case:read")
    rows = list(db.scalars(select(MissingItem).where(MissingItem.tenant_id == actor.tenant_id, MissingItem.case_id == case_id).order_by(MissingItem.blocking.desc(), MissingItem.created_at.asc())))
    return [{"id": row.id, "code": row.code, "title": row.title, "reason": row.reason, "priority": row.priority, "status": row.status, "blocking": row.blocking, "resolved_by": row.resolved_by, "resolved_at": row.resolved_at} for row in rows]


@router.post("/missing-items/{item_id}/resolve")
def resolve_missing_item(item_id: str, actor: Actor = Depends(require_permission("review:*")), db: Session = Depends(get_db)):
    row = db.scalar(select(MissingItem).where(MissingItem.id == item_id, MissingItem.tenant_id == actor.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Missing item not found")
    assert_case_access(db, actor, row.case_id, "review:*")
    row.status = "RESOLVED"; row.resolved_by = actor.user_id; row.resolved_at = datetime.now(timezone.utc)
    append_audit(db, actor=actor, action="missing_item.resolved", entity_type="missing_item", entity_id=row.id, case_id=row.case_id, after={"status": row.status})
    db.commit()
    return {"id": row.id, "status": row.status}


@router.get("/cases/{case_id}/audit-events")
def list_audit_events(case_id: str, limit: int = 200, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    assert_case_access(db, actor, case_id, "case:read")
    rows = list(db.scalars(select(AuditEvent).where(AuditEvent.tenant_id == actor.tenant_id, AuditEvent.case_id == case_id).order_by(AuditEvent.occurred_at.desc()).limit(min(max(limit, 1), 1000))))
    return [{"id": row.id, "actor_id": row.actor_id, "actor_role": row.actor_role, "action": row.action, "entity_type": row.entity_type, "entity_id": row.entity_id, "before_hash": row.before_hash, "after_hash": row.after_hash, "metadata": row.metadata_json, "occurred_at": row.occurred_at} for row in rows]
