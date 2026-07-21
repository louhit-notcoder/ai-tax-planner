from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import append_audit
from ..database import get_db
from ..db_models import LegalSource
from ..legal.retrieval import search_approved_sources
from ..security import Actor, get_actor, require_permission
from .schemas import LegalSourceCreate

router = APIRouter(prefix="/legal", tags=["legal-knowledge"])


@router.get("/search")
def search(query: str = Query(min_length=2), tax_period: str = "AY 2026-27", act_namespace: str = "ITA_1961", actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    return [item.__dict__ for item in search_approved_sources(db, query=query, tax_period=tax_period, act_namespace=act_namespace)]


@router.post("/sources", status_code=201)
def create_source(payload: LegalSourceCreate, actor: Actor = Depends(require_permission("tenant:read")), db: Session = Depends(get_db)):
    if actor.role not in {"firm_owner", "ca_partner"}:
        raise HTTPException(status_code=403, detail="Tax-law source ingestion requires partner approval")
    digest = hashlib.sha256(payload.content_text.encode("utf-8")).hexdigest()
    existing = db.scalar(select(LegalSource).where(LegalSource.source_hash == digest))
    if existing:
        return {"id": existing.id, "duplicate": True}
    row = LegalSource(source_type=payload.source_type, title=payload.title, act_namespace=payload.act_namespace, section_or_rule=payload.section_or_rule, publication_date=payload.publication_date, effective_from=payload.effective_from, effective_to=payload.effective_to, applicable_periods=payload.applicable_periods, official_url=payload.official_url, source_hash=digest, review_status=payload.review_status, content_text=payload.content_text, superseded=False)
    db.add(row); db.flush()
    append_audit(db, actor=actor, action="legal_source.created", entity_type="legal_source", entity_id=row.id, after={"title": row.title, "hash": digest, "review_status": row.review_status})
    db.commit()
    return {"id": row.id, "source_hash": row.source_hash, "review_status": row.review_status}
