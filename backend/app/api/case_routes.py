from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import append_audit
from ..database import get_db
from ..db_models import Client, ComputationRun, Document, MissingItem, ReconciliationItem, TaxCase
from ..security import Actor, assert_case_access, blind_index, encrypt_text, get_actor, require_permission
from .schemas import CaseAssignmentUpdate, CaseCreate, ClientCreate

router = APIRouter(tags=["clients-and-cases"])


@router.post("/clients", status_code=201)
def create_client(payload: ClientCreate, actor: Actor = Depends(require_permission("client:create")), db: Session = Depends(get_db)):
    if payload.pan:
        existing = db.scalar(select(Client).where(Client.tenant_id == actor.tenant_id, Client.pan_blind_index == blind_index(payload.pan)))
        if existing:
            raise HTTPException(status_code=409, detail="A client with this PAN already exists in the firm")
    client = Client(
        tenant_id=actor.tenant_id,
        display_name=payload.display_name,
        email=str(payload.email) if payload.email else None,
        phone_encrypted=encrypt_text(payload.phone) if payload.phone else None,
        pan_encrypted=encrypt_text(payload.pan) if payload.pan else None,
        pan_blind_index=blind_index(payload.pan) if payload.pan else None,
        date_of_birth_encrypted=encrypt_text(payload.date_of_birth.isoformat()) if payload.date_of_birth else None,
        metadata_json=payload.metadata,
    )
    db.add(client); db.flush()
    append_audit(db, actor=actor, action="client.created", entity_type="client", entity_id=client.id, after={"display_name": client.display_name})
    db.commit()
    return {"id": client.id, "display_name": client.display_name, "email": client.email, "status": client.status}


@router.get("/clients")
def list_clients(actor: Actor = Depends(require_permission("client:read")), db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Client).where(Client.tenant_id == actor.tenant_id, Client.status == "ACTIVE").order_by(Client.display_name)))
    return [{"id": row.id, "display_name": row.display_name, "email": row.email, "status": row.status, "metadata": row.metadata_json} for row in rows]


@router.post("/cases", status_code=201)
def create_case(payload: CaseCreate, actor: Actor = Depends(require_permission("case:create")), db: Session = Depends(get_db)):
    client = db.scalar(select(Client).where(Client.id == payload.client_id, Client.tenant_id == actor.tenant_id))
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    existing = db.scalar(select(TaxCase).where(TaxCase.tenant_id == actor.tenant_id, TaxCase.client_id == client.id, TaxCase.tax_period == payload.tax_period))
    if existing:
        raise HTTPException(status_code=409, detail="A case already exists for this client and tax period")
    case = TaxCase(
        tenant_id=actor.tenant_id,
        client_id=client.id,
        tax_period=payload.tax_period,
        assessment_year=payload.assessment_year,
        selected_regime=payload.selected_regime,
        preparer_id=payload.preparer_id or actor.user_id,
        reviewer_id=payload.reviewer_id,
        due_date=payload.due_date,
        status="INTAKE",
    )
    db.add(case); db.flush()
    append_audit(db, actor=actor, action="case.created", entity_type="tax_case", entity_id=case.id, case_id=case.id, after={"client_id": client.id, "tax_period": case.tax_period})
    db.commit()
    return _case_out(case, client)


def _case_out(case: TaxCase, client: Client | None = None):
    return {
        "id": case.id,
        "client_id": case.client_id,
        "client_name": client.display_name if client else None,
        "tax_period": case.tax_period,
        "assessment_year": case.assessment_year,
        "act_namespace": case.act_namespace,
        "status": case.status,
        "selected_regime": case.selected_regime,
        "recommended_form": case.recommended_form,
        "rule_release_id": case.rule_release_id,
        "preparer_id": case.preparer_id,
        "reviewer_id": case.reviewer_id,
        "due_date": case.due_date,
        "locked_at": case.locked_at,
        "risk_flags": case.risk_flags,
    }


@router.get("/cases")
def list_cases(actor: Actor = Depends(require_permission("case:read")), db: Session = Depends(get_db)):
    query = select(TaxCase, Client).join(Client, TaxCase.client_id == Client.id).where(TaxCase.tenant_id == actor.tenant_id)
    if actor.role not in {"firm_owner", "ca_partner", "ca_manager", "auditor"}:
        query = query.where((TaxCase.preparer_id == actor.user_id) | (TaxCase.reviewer_id == actor.user_id))
    rows = db.execute(query.order_by(TaxCase.updated_at.desc())).all()
    return [_case_out(case, client) for case, client in rows]


@router.get("/cases/{case_id}")
def get_case(case_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    case = assert_case_access(db, actor, case_id)
    client = db.get(Client, case.client_id)
    latest = db.scalar(select(ComputationRun).where(ComputationRun.case_id == case.id).order_by(ComputationRun.created_at.desc()))
    return {**_case_out(case, client), "latest_computation": latest.result_json if latest else None}


@router.patch("/cases/{case_id}/assignment")
def update_assignment(case_id: str, payload: CaseAssignmentUpdate, actor: Actor = Depends(require_permission("case:update")), db: Session = Depends(get_db)):
    case = assert_case_access(db, actor, case_id, "case:update")
    before = {"preparer_id": case.preparer_id, "reviewer_id": case.reviewer_id}
    case.preparer_id = payload.preparer_id
    case.reviewer_id = payload.reviewer_id
    append_audit(db, actor=actor, action="case.assignment_updated", entity_type="tax_case", entity_id=case.id, case_id=case.id, before=before, after={"preparer_id": case.preparer_id, "reviewer_id": case.reviewer_id})
    db.commit()
    return _case_out(case)


@router.post("/cases/{case_id}/lock")
def lock_case(case_id: str, actor: Actor = Depends(require_permission("review:*")), db: Session = Depends(get_db)):
    case = assert_case_access(db, actor, case_id, "review:*")
    if case.status != "APPROVED":
        raise HTTPException(status_code=409, detail="Only an approved case can be locked")
    case.locked_at = datetime.now(timezone.utc)
    case.locked_by = actor.user_id
    case.status = "LOCKED"
    append_audit(db, actor=actor, action="case.locked", entity_type="tax_case", entity_id=case.id, case_id=case.id, after={"locked_at": case.locked_at})
    db.commit()
    return _case_out(case)


@router.get("/dashboard")
def dashboard(actor: Actor = Depends(require_permission("case:read")), db: Session = Depends(get_db)):
    statuses = dict(db.execute(select(TaxCase.status, func.count()).where(TaxCase.tenant_id == actor.tenant_id).group_by(TaxCase.status)).all())
    missing = db.scalar(select(func.count()).select_from(MissingItem).where(MissingItem.tenant_id == actor.tenant_id, MissingItem.status == "OPEN")) or 0
    discrepancies = db.scalar(select(func.count()).select_from(ReconciliationItem).where(ReconciliationItem.tenant_id == actor.tenant_id, ReconciliationItem.status.in_(["DIFFERENCE", "REVIEW_REQUIRED"]))) or 0
    documents = db.scalar(select(func.count()).select_from(Document).where(Document.tenant_id == actor.tenant_id, Document.state.in_(["VALIDATION_REQUIRED", "PARSER_FAILED"]))) or 0
    return {"case_status_counts": statuses, "open_missing_items": missing, "unresolved_discrepancies": discrepancies, "documents_needing_attention": documents}
