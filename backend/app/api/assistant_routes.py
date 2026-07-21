from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..db_models import ClientQuestionDraft, DocumentRequestDraft
from ..security import Actor, assert_case_access, get_actor, require_permission
from ..services.assistant_service import gateway
from .schemas import DraftApprovalRequest, ToolCallRequest

router = APIRouter(tags=["assistant"])


@router.post("/cases/{case_id}/assistant/tools")
def execute_tool(case_id: str, payload: ToolCallRequest, actor: Actor = Depends(require_permission("assistant:*")), db: Session = Depends(get_db)):
    result = gateway.execute(db, actor=actor, case_id=case_id, name=payload.name, arguments=payload.arguments, idempotency_key=payload.idempotency_key)
    db.commit()
    return result


@router.get("/cases/{case_id}/assistant/drafts")
def list_drafts(case_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    assert_case_access(db, actor, case_id, "assistant:*")
    questions = list(db.scalars(select(ClientQuestionDraft).where(ClientQuestionDraft.tenant_id == actor.tenant_id, ClientQuestionDraft.case_id == case_id).order_by(ClientQuestionDraft.created_at.desc())))
    documents = list(db.scalars(select(DocumentRequestDraft).where(DocumentRequestDraft.tenant_id == actor.tenant_id, DocumentRequestDraft.case_id == case_id).order_by(DocumentRequestDraft.created_at.desc())))
    return {
        "client_questions": [{"id": row.id, "topic": row.topic, "question": row.question, "context": row.context, "priority": row.priority, "status": row.status, "created_by": row.created_by} for row in questions],
        "document_requests": [{"id": row.id, "document_type": row.document_type, "purpose": row.purpose, "deadline": row.deadline, "status": row.status, "created_by": row.created_by} for row in documents],
    }


@router.post("/assistant/question-drafts/{draft_id}/review")
def review_question(draft_id: str, payload: DraftApprovalRequest, actor: Actor = Depends(require_permission("review:*")), db: Session = Depends(get_db)):
    row = db.scalar(select(ClientQuestionDraft).where(ClientQuestionDraft.id == draft_id, ClientQuestionDraft.tenant_id == actor.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Draft not found")
    assert_case_access(db, actor, row.case_id, "review:*")
    if payload.edited_text:
        row.question = payload.edited_text
    row.status = "APPROVED" if payload.decision == "APPROVE" else "REJECTED"
    row.approved_by = actor.user_id if payload.decision == "APPROVE" else None
    db.commit()
    return {"id": row.id, "status": row.status, "question": row.question}


@router.post("/assistant/document-drafts/{draft_id}/review")
def review_document_request(draft_id: str, payload: DraftApprovalRequest, actor: Actor = Depends(require_permission("review:*")), db: Session = Depends(get_db)):
    row = db.scalar(select(DocumentRequestDraft).where(DocumentRequestDraft.id == draft_id, DocumentRequestDraft.tenant_id == actor.tenant_id))
    if not row:
        raise HTTPException(status_code=404, detail="Draft not found")
    assert_case_access(db, actor, row.case_id, "review:*")
    if payload.edited_text:
        row.purpose = payload.edited_text
    row.status = "APPROVED" if payload.decision == "APPROVE" else "REJECTED"
    row.approved_by = actor.user_id if payload.decision == "APPROVE" else None
    db.commit()
    return {"id": row.id, "status": row.status, "purpose": row.purpose}
