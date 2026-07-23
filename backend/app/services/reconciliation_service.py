"""Cross-document reconciliation service (DB-facing)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import append_audit
from ..db_models import CandidateFact, ReconciliationItem
from ..security import Actor, assert_case_access
from .reconciliation import compute_reconciliation

# Cross-document items are namespaced so they never collide with the per-field
# candidate-vs-accepted reconciliation rows written during fact review.
CATEGORY_PREFIX = "XDOC:"


def rebuild_reconciliation(db: Session, actor: Actor, case_id: str) -> dict[str, Any]:
    """Recompute cross-document reconciliation for a case and persist the result.

    Uses the latest non-rejected candidate fact per (field_code, entity_key), so
    it reflects what each uploaded document actually reported.
    """
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
        latest[(candidate.field_code, entity_key)] = candidate  # ordered asc -> latest wins

    facts = [{"field_code": c.field_code, "value_json": c.value_json} for c in latest.values()]
    results = compute_reconciliation(facts)

    for row in results:
        category = f"{CATEGORY_PREFIX}{row['category']}"
        item = db.scalar(select(ReconciliationItem).where(
            ReconciliationItem.tenant_id == actor.tenant_id,
            ReconciliationItem.case_id == case_id,
            ReconciliationItem.category == category,
            ReconciliationItem.entity_key == "ROOT",
            ReconciliationItem.resolved_at.is_(None),
        ))
        difference = Decimal(row["difference"])
        if item is None:
            db.add(ReconciliationItem(
                tenant_id=actor.tenant_id,
                case_id=case_id,
                category=category,
                entity_key="ROOT",
                source_values=row["sources"],
                status=row["status"],
                difference_amount=difference,
            ))
        else:
            item.source_values = row["sources"]
            item.status = row["status"]
            item.difference_amount = difference

    differences = [r for r in results if r["status"] == "DIFFERENCE"]
    append_audit(
        db, actor=actor, action="reconciliation.rebuilt", entity_type="tax_case", entity_id=case_id, case_id=case_id,
        after={"categories": len(results), "differences": len(differences)},
    )
    db.flush()
    return {"case_id": case_id, "reconciliation": results, "difference_count": len(differences)}


def safe_rebuild(db: Session, actor: Actor, case_id: str) -> None:
    """Best-effort rebuild as a side effect of extraction.

    Runs in a savepoint so a reconciliation failure rolls back only its own work,
    never the document extraction that triggered it, and never raises.
    """
    try:
        with db.begin_nested():
            rebuild_reconciliation(db, actor, case_id)
    except Exception:
        pass
