from __future__ import annotations

from datetime import datetime, timezone
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import append_audit
from ..db_models import Approval, CalculationLineRecord, ComputationRun, FactSnapshot, MissingItem, RuleRelease, TaxCase
from ..security import Actor, assert_case_access, assert_case_mutable
from ..tax_engine.engine import DeterministicTaxEngine, ENGINE_VERSION
from ..tax_engine.rules import load_rule_release
from .facts_service import build_tax_snapshot, load_tax_snapshot

engine = DeterministicTaxEngine()


def ensure_rule_release(db: Session, release_id: str) -> RuleRelease:
    record = db.get(RuleRelease, release_id)
    if record:
        return record
    rules = load_rule_release(release_id)
    record = RuleRelease(
        id=rules["release_id"],
        tax_period=rules["financial_year"],
        assessment_year=rules["assessment_year"],
        act_namespace=rules["act_namespace"],
        status=rules.get("status", "DRAFT"),
        rules_json=json.loads(json.dumps({k: v for k, v in rules.items() if k != "rule_bundle_hash"}, default=str)),
        rules_hash=rules["rule_bundle_hash"],
        source_documents=rules.get("sources", []),
        code_commit=ENGINE_VERSION,
        reviewed_by=[],
    )
    db.add(record)
    db.flush()
    return record


def run_computation(db: Session, *, actor: Actor, case_id: str, selected_regime: str | None = None) -> ComputationRun:
    case = assert_case_access(db, actor, case_id, "computation:run")
    assert_case_mutable(case)
    snapshot_record, snapshot = build_tax_snapshot(db, actor=actor, case_id=case_id, selected_regime=selected_regime)
    rule_record = ensure_rule_release(db, case.rule_release_id)
    rules = load_rule_release(case.rule_release_id)
    result = engine.compute(snapshot, rules)
    run = ComputationRun(
        tenant_id=actor.tenant_id,
        case_id=case_id,
        fact_snapshot_id=snapshot_record.id,
        rule_release_id=rule_record.id,
        engine_version=ENGINE_VERSION,
        regime=result.selected_regime.value,
        status=result.status.value,
        result_json=result.model_dump(mode="json"),
        result_hash=result.result_hash,
        immutable=True,
    )
    db.add(run)
    db.flush()
    for order, line in enumerate(result.calculation_lines):
        db.add(CalculationLineRecord(
            tenant_id=actor.tenant_id,
            computation_run_id=run.id,
            line_order=order,
            line_code=line.code,
            label=line.label,
            formula=line.formula,
            input_fact_ids=line.input_fact_ids,
            input_line_ids=line.input_line_ids,
            rule_ids=line.rule_ids,
            amount_json=line.model_dump(mode="json"),
        ))
    _sync_missing_items(db, actor=actor, case_id=case_id, result=result)
    case.recommended_form = result.form_eligibility.recommended_form
    case.selected_regime = result.selected_regime.value
    case.status = "REVIEW_REQUIRED" if result.status.value != "COMPLETE" else "COMPUTED"
    append_audit(db, actor=actor, action="computation.run", entity_type="computation_run", entity_id=run.id, case_id=case_id, after={"status": run.status, "result_hash": run.result_hash, "snapshot_id": snapshot_record.id, "rule_release": rule_record.id})
    return run




def _sync_missing_items(db: Session, *, actor: Actor, case_id: str, result) -> None:
    active: dict[str, dict] = {}
    for issue in result.blockers:
        active[f"AUTO_{issue.code}"] = {"title": issue.code.replace("_", " ").title(), "reason": issue.message, "priority": "HIGH", "blocking": True}
    for issue in result.warnings:
        if issue.review_required:
            active[f"AUTO_{issue.code}"] = {"title": issue.code.replace("_", " ").title(), "reason": issue.message, "priority": "MEDIUM", "blocking": False}
    for index, message in enumerate(result.missing_information):
        active[f"AUTO_MISSING_{index}_{stable_code(message)}"] = {"title": "Missing tax information", "reason": message, "priority": "HIGH", "blocking": True}
    existing = list(db.scalars(select(MissingItem).where(MissingItem.tenant_id == actor.tenant_id, MissingItem.case_id == case_id, MissingItem.code.like("AUTO_%"))))
    by_code = {row.code: row for row in existing}
    now = datetime.now(timezone.utc)
    for code, data in active.items():
        row = by_code.get(code)
        if not row:
            db.add(MissingItem(tenant_id=actor.tenant_id, case_id=case_id, code=code, title=data["title"], reason=data["reason"], priority=data["priority"], status="OPEN", blocking=data["blocking"]))
        else:
            row.title=data["title"]; row.reason=data["reason"]; row.priority=data["priority"]; row.blocking=data["blocking"]; row.status="OPEN"; row.resolved_by=None; row.resolved_at=None
    for code, row in by_code.items():
        if code not in active and row.status == "OPEN":
            row.status="RESOLVED"; row.resolved_by=actor.user_id; row.resolved_at=now


def stable_code(message: str) -> str:
    import hashlib
    return hashlib.sha256(message.encode("utf-8")).hexdigest()[:12].upper()


def approve_computation(db: Session, *, actor: Actor, run_id: str, decision: str, justification: str) -> ComputationRun:
    run = db.scalar(select(ComputationRun).where(ComputationRun.id == run_id, ComputationRun.tenant_id == actor.tenant_id))
    if not run:
        raise HTTPException(status_code=404, detail="Computation run not found")
    case = assert_case_access(db, actor, run.case_id, "review:*")
    result_status = run.result_json.get("status")
    if decision == "APPROVE":
        if result_status != "COMPLETE":
            raise HTTPException(status_code=409, detail="Only COMPLETE computations can receive final approval")
        if case.reviewer_id and case.reviewer_id != actor.user_id and actor.role not in {"firm_owner", "ca_partner"}:
            raise HTTPException(status_code=403, detail="Only the assigned reviewer may approve this computation")
        if case.preparer_id == actor.user_id and actor.role not in {"firm_owner", "ca_partner"}:
            raise HTTPException(status_code=409, detail="Maker-checker policy prevents preparer self-approval")
        run.approved_by = actor.user_id
        run.approved_at = datetime.now(timezone.utc)
        approval = Approval(
            tenant_id=actor.tenant_id,
            case_id=case.id,
            approval_type="FINAL_COMPUTATION",
            entity_type="computation_run",
            entity_id=run.id,
            decision="APPROVED",
            justification=justification,
            approved_by=actor.user_id,
        )
        db.add(approval)
        db.flush()
        case.final_approval_id = approval.id
        case.status = "APPROVED"
    else:
        case.status = "REVIEW_REQUIRED"
        db.add(Approval(
            tenant_id=actor.tenant_id,
            case_id=case.id,
            approval_type="FINAL_COMPUTATION",
            entity_type="computation_run",
            entity_id=run.id,
            decision="REJECTED",
            justification=justification,
            approved_by=actor.user_id,
        ))
    append_audit(db, actor=actor, action=f"computation.{decision.lower()}", entity_type="computation_run", entity_id=run.id, case_id=case.id, after={"approved_by": run.approved_by, "case_status": case.status}, metadata={"justification": justification})
    return run


def get_latest_computation(db: Session, *, actor: Actor, case_id: str) -> ComputationRun | None:
    assert_case_access(db, actor, case_id, "computation:read")
    return db.scalar(select(ComputationRun).where(ComputationRun.tenant_id == actor.tenant_id, ComputationRun.case_id == case_id).order_by(ComputationRun.created_at.desc()))
