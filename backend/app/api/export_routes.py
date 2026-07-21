from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..db_models import ExportSnapshot
from ..security import Actor, assert_case_access, get_actor, require_permission
from ..services.export_service import approve_export, create_export
from .schemas import ExportApprovalRequest, ExportCreateRequest

router = APIRouter(tags=["exports"])


@router.post("/cases/{case_id}/exports", status_code=201)
def build_export(case_id: str, payload: ExportCreateRequest, actor: Actor = Depends(require_permission("export:prepare")), db: Session = Depends(get_db)):
    row = create_export(db, actor=actor, case_id=case_id, computation_run_id=payload.computation_run_id, form_code=payload.form_code, identity=payload.identity.model_dump(mode="json"), intermediary_city=payload.intermediary_city, schema_version=payload.schema_version)
    db.commit()
    return {"id": row.id, "status": row.status, "form_code": row.form_code, "schema_version": row.schema_version, "validation_version": row.validation_version, "validation_errors": row.validation_errors, "snapshot_hash": row.snapshot_hash}


@router.get("/cases/{case_id}/exports")
def list_exports(case_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    assert_case_access(db, actor, case_id, "export:read")
    rows = list(db.scalars(select(ExportSnapshot).where(ExportSnapshot.tenant_id == actor.tenant_id, ExportSnapshot.case_id == case_id).order_by(ExportSnapshot.created_at.desc())))
    return [{"id": row.id, "status": row.status, "form_code": row.form_code, "schema_version": row.schema_version, "validation_version": row.validation_version, "snapshot_hash": row.snapshot_hash, "approved_by": row.approved_by, "approved_at": row.approved_at, "created_at": row.created_at} for row in rows]


@router.post("/exports/{export_id}/review")
def review_export(export_id: str, payload: ExportApprovalRequest, actor: Actor = Depends(require_permission("export:*")), db: Session = Depends(get_db)):
    row = approve_export(db, actor=actor, export_id=export_id, decision=payload.decision, justification=payload.justification)
    db.commit()
    return {"id": row.id, "status": row.status, "approved_by": row.approved_by, "approved_at": row.approved_at}


@router.get("/exports/{export_id}/download")
def download_export(export_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = db.scalar(select(ExportSnapshot).where(ExportSnapshot.id == export_id, ExportSnapshot.tenant_id == actor.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Export not found")
    assert_case_access(db, actor, row.case_id, "export:read")
    if row.status != "APPROVED":
        raise HTTPException(status_code=409, detail="Only approved exports can be downloaded as filing artifacts")
    row.exported_at = datetime.now(timezone.utc)
    db.commit()
    body = json.dumps(row.payload_json, ensure_ascii=False, separators=(",", ":"))
    return Response(content=body, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{row.form_code}_{row.assessment_year.replace(" ", "_")}.json"', "X-Green-Papaya-Snapshot-Hash": row.snapshot_hash})
