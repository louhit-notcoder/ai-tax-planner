from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..db_models import ComputationRun
from ..security import Actor, assert_case_access, get_actor, require_permission
from ..services.computation_service import approve_computation, get_latest_computation, run_computation
from .schemas import ComputationApprovalRequest, SnapshotRequest

router = APIRouter(tags=["computations"])


@router.post("/cases/{case_id}/computations", status_code=201)
def compute(case_id: str, payload: SnapshotRequest, actor: Actor = Depends(require_permission("computation:run")), db: Session = Depends(get_db)):
    run = run_computation(db, actor=actor, case_id=case_id, selected_regime=payload.selected_regime)
    db.commit()
    return {"id": run.id, "status": run.status, "result_hash": run.result_hash, "result": run.result_json}


@router.get("/cases/{case_id}/computations/latest")
def latest(case_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = get_latest_computation(db, actor=actor, case_id=case_id)
    if not row:
        raise HTTPException(status_code=404, detail="No computation exists")
    return {"id": row.id, "status": row.status, "result_hash": row.result_hash, "approved_by": row.approved_by, "approved_at": row.approved_at, "result": row.result_json}


@router.get("/computations/{run_id}")
def get_run(run_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    row = db.scalar(select(ComputationRun).where(ComputationRun.id == run_id, ComputationRun.tenant_id == actor.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Computation not found")
    assert_case_access(db, actor, row.case_id, "computation:read")
    return {"id": row.id, "case_id": row.case_id, "status": row.status, "result_hash": row.result_hash, "approved_by": row.approved_by, "approved_at": row.approved_at, "result": row.result_json}


@router.post("/computations/{run_id}/review")
def review(run_id: str, payload: ComputationApprovalRequest, actor: Actor = Depends(require_permission("review:*")), db: Session = Depends(get_db)):
    row = approve_computation(db, actor=actor, run_id=run_id, decision=payload.decision, justification=payload.justification)
    db.commit()
    return {"id": row.id, "status": row.status, "approved_by": row.approved_by, "approved_at": row.approved_at}
