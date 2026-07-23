"""Case summary service (DB-facing)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import CandidateFact, MissingItem
from ..security import Actor, assert_case_access
from .case_summary import compose_case_summary
from .reconciliation import compute_reconciliation


def build_case_summary(db: Session, actor: Actor, case_id: str) -> dict[str, Any]:
    """Consolidated summary across every document processed for the case."""
    assert_case_access(db, actor, case_id, "case:read")

    candidates = list(db.scalars(
        select(CandidateFact)
        .where(
            CandidateFact.tenant_id == actor.tenant_id,
            CandidateFact.case_id == case_id,
            CandidateFact.status != "REJECTED",
        )
        .order_by(CandidateFact.created_at)
    ))
    latest: dict[tuple[str, str], CandidateFact] = {}
    for candidate in candidates:
        entity_key = (candidate.value_json or {}).get("entity_key", "ROOT")
        latest[(candidate.field_code, entity_key)] = candidate
    facts = [{"field_code": c.field_code, "value_json": c.value_json} for c in latest.values()]

    reconciliation = compute_reconciliation(facts)
    missing = [
        f"{item.title}: {item.reason}"
        for item in db.scalars(select(MissingItem).where(
            MissingItem.tenant_id == actor.tenant_id,
            MissingItem.case_id == case_id,
            MissingItem.status == "OPEN",
        ))
    ]
    return compose_case_summary(facts, reconciliation, missing)
