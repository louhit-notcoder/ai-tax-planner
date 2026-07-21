from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .db_models import AuditEvent
from .security import Actor, stable_json_hash


def append_audit(
    db: Session,
    *,
    actor: Actor,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    case_id: str | None = None,
    before: Any = None,
    after: Any = None,
    metadata: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        tenant_id=actor.tenant_id,
        case_id=case_id,
        actor_id=actor.user_id,
        actor_role=actor.role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_hash=stable_json_hash(before) if before is not None else None,
        after_hash=stable_json_hash(after) if after is not None else None,
        metadata_json=metadata or {},
    )
    db.add(event)
    db.flush()
    return event
