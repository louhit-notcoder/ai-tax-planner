from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .hashing import sha256_json


async def append_audit_event(
    db,
    *,
    tenant_id: str,
    case_id: str | None,
    actor_id: str,
    actor_role: str,
    action: str,
    entity_type: str,
    entity_id: str | None,
    before: Any = None,
    after: Any = None,
    metadata: dict | None = None,
) -> dict:
    event = {
        "event_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "case_id": case_id,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "before_hash": sha256_json(before) if before is not None else None,
        "after_hash": sha256_json(after) if after is not None else None,
        "metadata": metadata or {},
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.audit_events.insert_one(event.copy())
    return event
