from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..db_models import CandidateFact, Document, EvidenceClaim, ExtractionRun
from ..security import Actor, assert_case_access, get_actor, require_permission
from ..services.document_service import extract_document, upload_document
from ..storage import storage

router = APIRouter(tags=["documents"])


@router.post("/cases/{case_id}/documents", status_code=201)
async def upload(case_id: str, file: UploadFile = File(...), actor: Actor = Depends(require_permission("document:*")), db: Session = Depends(get_db)):
    data = await file.read()
    document = upload_document(db, actor=actor, case_id=case_id, filename=file.filename or "upload.bin", content_type=file.content_type or "application/octet-stream", data=data)
    db.commit()
    return _document_out(document)


def _document_out(row: Document):
    return {
        "id": row.id,
        "case_id": row.case_id,
        "document_type": row.document_type,
        "state": row.state,
        "filename": row.original_filename,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
        "classification_confidence": str(row.classification_confidence) if row.classification_confidence is not None else None,
        "classification_metadata": row.classification_metadata,
        "created_at": row.created_at,
    }


@router.get("/cases/{case_id}/documents")
def list_documents(case_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    assert_case_access(db, actor, case_id, "document:read")
    rows = list(db.scalars(select(Document).where(Document.tenant_id == actor.tenant_id, Document.case_id == case_id).order_by(Document.created_at.desc())))
    return [_document_out(row) for row in rows]


@router.post("/documents/{document_id}/extract")
def extract(document_id: str, actor: Actor = Depends(require_permission("document:*")), db: Session = Depends(get_db)):
    document, run, candidates = extract_document(db, actor=actor, document_id=document_id)
    db.commit()
    return {"document": _document_out(document), "extraction_run": {"id": run.id, "adapter": run.adapter_code, "version": run.adapter_version, "status": run.status, "metrics": run.metrics}, "candidate_fact_ids": [item.id for item in candidates]}


@router.get("/documents/{document_id}/content")
def content(document_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    document = db.scalar(select(Document).where(Document.id == document_id, Document.tenant_id == actor.tenant_id))
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    assert_case_access(db, actor, document.case_id, "document:read")
    data = storage.get(document.storage_key)
    return Response(content=data, media_type=document.mime_type, headers={"Content-Disposition": f'inline; filename="{document.original_filename}"', "Cache-Control": "private, no-store"})


@router.get("/documents/{document_id}/evidence")
def evidence(document_id: str, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    document = db.scalar(select(Document).where(Document.id == document_id, Document.tenant_id == actor.tenant_id))
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    assert_case_access(db, actor, document.case_id, "document:read")
    rows = list(db.scalars(select(EvidenceClaim).where(EvidenceClaim.document_id == document.id).order_by(EvidenceClaim.page_index, EvidenceClaim.field_code)))
    return [{"id": row.id, "field_code": row.field_code, "value_type": row.value_type, "value": row.value_json, "page_index": row.page_index, "bounding_box": row.bounding_box, "original_text": row.original_text, "extraction_method": row.extraction_method, "confidence": str(row.confidence) if row.confidence is not None else None, "validation_results": row.validation_results, "status": row.status} for row in rows]
