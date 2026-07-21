from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import append_audit
from ..db_models import Approval, ComputationRun, ExportSnapshot, FactSnapshot, TaxCase
from ..itr.exporter import ExportRequest, ITRIdentity, SchemaDrivenITRExporter
from ..itr.utility_validator import OfficialUtilityValidationAdapter
from ..security import Actor, assert_case_access
from ..tax_engine.models import ComputationResult, TaxFactSnapshot


exporter = SchemaDrivenITRExporter()
utility_validator = OfficialUtilityValidationAdapter()


def create_export(db: Session, *, actor: Actor, case_id: str, computation_run_id: str, form_code: str, identity: dict, intermediary_city: str, schema_version: str) -> ExportSnapshot:
    case = assert_case_access(db, actor, case_id, "export:prepare")
    run = db.scalar(select(ComputationRun).where(ComputationRun.id == computation_run_id, ComputationRun.case_id == case_id, ComputationRun.tenant_id == actor.tenant_id))
    if not run:
        raise HTTPException(status_code=404, detail="Computation run not found")
    if not run.approved_by or case.final_approval_id is None:
        raise HTTPException(status_code=409, detail="Final CA computation approval is required")
    fact_record = db.get(FactSnapshot, run.fact_snapshot_id)
    if not fact_record:
        raise HTTPException(status_code=500, detail="Fact snapshot is missing")
    computation = ComputationResult(**run.result_json)
    facts = TaxFactSnapshot(**fact_record.facts_json)
    try:
        build = exporter.build(ExportRequest(
            form_code=form_code,
            identity=ITRIdentity(**identity),
            computation=computation,
            facts=facts,
            intermediary_city=intermediary_city,
            schema_version=schema_version,
            creation_date=datetime.now(timezone.utc).date(),
            ca_reviewer_approved=True,
        ))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    utility = utility_validator.validate(build.payload) if not build.validation_errors else None
    validation_errors = [item.__dict__ for item in build.validation_errors]
    if utility:
        validation_errors.extend(utility.errors)
    if build.validation_errors:
        status = "VALIDATION_FAILED"
    elif not utility or not utility.configured:
        status = "READY_FOR_UTILITY_VALIDATION"
    elif not utility.passed:
        status = "UTILITY_VALIDATION_FAILED"
    else:
        status = "READY_FOR_CA_REVIEW"
    snapshot = ExportSnapshot(
        tenant_id=actor.tenant_id,
        case_id=case_id,
        computation_run_id=run.id,
        form_code=form_code,
        assessment_year=case.assessment_year,
        schema_version=build.schema_version,
        validation_version="AY2026_27_PUBLISHED_V1.0",
        exporter_version="3.0.0",
        status=status,
        payload_json=build.payload,
        validation_errors=validation_errors,
        snapshot_hash=build.snapshot_hash,
        immutable=True,
    )
    db.add(snapshot); db.flush()
    append_audit(db, actor=actor, action="export.created", entity_type="export_snapshot", entity_id=snapshot.id, case_id=case_id, after={"status": status, "schema_hash": build.schema_hash, "snapshot_hash": build.snapshot_hash, "utility_configured": bool(utility and utility.configured)})
    return snapshot


def approve_export(db: Session, *, actor: Actor, export_id: str, decision: str, justification: str) -> ExportSnapshot:
    snapshot = db.scalar(select(ExportSnapshot).where(ExportSnapshot.id == export_id, ExportSnapshot.tenant_id == actor.tenant_id))
    if not snapshot:
        raise HTTPException(status_code=404, detail="Export snapshot not found")
    case = assert_case_access(db, actor, snapshot.case_id, "export:*")
    if decision == "APPROVE":
        if snapshot.status != "READY_FOR_CA_REVIEW":
            raise HTTPException(status_code=409, detail="Export must pass schema and configured official utility validation before approval")
        snapshot.status = "APPROVED"
        snapshot.approved_by = actor.user_id
        snapshot.approved_at = datetime.now(timezone.utc)
    else:
        snapshot.status = "VALIDATION_FAILED"
    approval = Approval(tenant_id=actor.tenant_id, case_id=case.id, approval_type="ITR_EXPORT", entity_type="export_snapshot", entity_id=snapshot.id, decision="APPROVED" if decision == "APPROVE" else "REJECTED", justification=justification, approved_by=actor.user_id)
    db.add(approval)
    append_audit(db, actor=actor, action=f"export.{decision.lower()}", entity_type="export_snapshot", entity_id=snapshot.id, case_id=case.id, after={"status": snapshot.status}, metadata={"justification": justification})
    return snapshot
