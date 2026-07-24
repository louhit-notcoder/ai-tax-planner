from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import append_audit
from ..db_models import CandidateFact, Document, DocumentPassword, DocumentVersion, EvidenceClaim, ExtractionRun
from ..document_adapters.registry import AdapterRegistry
from ..document_adapters.pdf_security import is_encrypted, is_pdf, unlock_pdf
from ..document_security import inspect_document
from ..security import Actor, assert_case_access, assert_case_mutable, decrypt_text, encrypt_text
from ..storage import storage
from .reconciliation_service import safe_rebuild


def case_passwords(db: Session, actor: Actor, case_id: str) -> list[str]:
    """Decrypted PDF passwords remembered for this case."""
    rows = db.scalars(select(DocumentPassword).where(
        DocumentPassword.tenant_id == actor.tenant_id,
        DocumentPassword.case_id == case_id,
    ))
    passwords: list[str] = []
    for row in rows:
        try:
            passwords.append(decrypt_text(row.password_encrypted))
        except Exception:
            continue
    return passwords


def remember_password(db: Session, actor: Actor, case_id: str, password: str) -> None:
    if password in case_passwords(db, actor, case_id):
        return
    db.add(DocumentPassword(tenant_id=actor.tenant_id, case_id=case_id, password_encrypted=encrypt_text(password), created_by=actor.user_id))

registry = AdapterRegistry()


def upload_document(db: Session, *, actor: Actor, case_id: str, filename: str, content_type: str, data: bytes) -> Document:
    case = assert_case_access(db, actor, case_id, "document:*")
    assert_case_mutable(case)
    # Password-protected PDF (Form 16 / AIS / TIS / bank statements): try passwords
    # already known for this case; if none open it, store it and mark it locked so
    # the CA is prompted once. Everything downstream then sees decrypted bytes.
    locked = False
    if is_pdf(filename, content_type, data) and is_encrypted(data):
        unlocked = None
        for password in case_passwords(db, actor, case_id):
            unlocked = unlock_pdf(data, password)
            if unlocked is not None:
                break
        if unlocked is not None:
            data = unlocked
        else:
            locked = True
    inspection = inspect_document(filename, content_type, data)
    duplicate = db.scalar(select(Document).where(Document.tenant_id == actor.tenant_id, Document.case_id == case_id, Document.sha256 == inspection.sha256))
    if duplicate:
        raise HTTPException(status_code=409, detail={"message": "Duplicate document already exists in this case", "document_id": duplicate.id})
    document_id = str(uuid.uuid4())
    key = f"tenants/{actor.tenant_id}/cases/{case_id}/documents/{document_id}/v1/{inspection.sha256}-{filename}"
    stored = storage.put(key=key, data=data, content_type=content_type or "application/octet-stream", metadata={"tenant_id": actor.tenant_id, "case_id": case_id})
    document = Document(
        id=document_id,
        tenant_id=actor.tenant_id,
        case_id=case_id,
        uploaded_by=actor.user_id,
        document_type="UNKNOWN",
        state="PASSWORD_REQUIRED" if locked else "SECURITY_CHECKED",
        original_filename=filename,
        mime_type=content_type or "application/octet-stream",
        size_bytes=inspection.size_bytes,
        sha256=inspection.sha256,
        storage_key=stored.key,
        is_password_protected=locked,
        classification_metadata={"detected_kind": inspection.detected_kind, "malware_scan": inspection.malware_scan},
    )
    version = DocumentVersion(
        tenant_id=actor.tenant_id,
        document_id=document.id,
        version_number=1,
        sha256=document.sha256,
        storage_key=document.storage_key,
    )
    db.add(document)
    db.flush()
    db.add(version)
    db.flush()
    document.current_version_id = version.id
    append_audit(db, actor=actor, action="document.uploaded", entity_type="document", entity_id=document.id, case_id=case_id, after={"filename": filename, "sha256": inspection.sha256, "malware_scan": inspection.malware_scan})
    return document


def extract_document(db: Session, *, actor: Actor, document_id: str) -> tuple[Document, ExtractionRun, list[CandidateFact]]:
    document = db.scalar(select(Document).where(Document.id == document_id, Document.tenant_id == actor.tenant_id))
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    case = assert_case_access(db, actor, document.case_id, "document:*")
    assert_case_mutable(case)
    if document.state == "PASSWORD_REQUIRED":
        raise HTTPException(status_code=409, detail={"message": "This document is password protected. Provide the password to unlock it first.", "document_id": document.id, "requires_password": True})
    data = storage.get(document.storage_key)
    adapter, score = registry.classify(document.original_filename, document.mime_type, data)
    if not adapter:
        document.state = "UNSUPPORTED_FORMAT"
        document.classification_confidence = score
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No production adapter recognised this document. Please ensure the file is a valid PDF, JSON, CSV, or XLSX file.",
                "filename": document.original_filename,
                "mime_type": document.mime_type,
                "score": str(score),
                "hint": "If this is a Form 16 PDF with custom fonts, Vision API may be required."
            }
        )
    run = ExtractionRun(
        tenant_id=actor.tenant_id,
        case_id=document.case_id,
        document_id=document.id,
        document_version_id=document.current_version_id,
        adapter_code=adapter.code,
        adapter_version=adapter.version,
        status="RUNNING",
    )
    db.add(run)
    db.flush()
    try:
        result = adapter.extract(document.original_filename, document.mime_type, data)
        candidates: list[CandidateFact] = []
        for claim in result.claims:
            evidence = EvidenceClaim(
                tenant_id=actor.tenant_id,
                case_id=document.case_id,
                document_id=document.id,
                document_version_id=document.current_version_id,
                extraction_run_id=run.id,
                field_code=claim.field_code,
                value_type=claim.value_type,
                value_json=claim.value,
                page_index=claim.source.page_index,
                bounding_box=claim.source.bounding_box,
                original_text=claim.source.original_text,
                extraction_method=adapter.code,
                confidence=claim.confidence,
                validation_results=claim.validations,
                status="VALIDATED" if all(item.get("status") == "PASS" for item in claim.validations) else "EXTRACTED",
            )
            db.add(evidence)
            db.flush()
            idempotency = f"extract:{run.id}:{claim.field_code}:{claim.entity_key}"
            candidate = CandidateFact(
                tenant_id=actor.tenant_id,
                case_id=document.case_id,
                field_code=claim.field_code,
                value_type=claim.value_type,
                value_json={**claim.value, "entity_key": claim.entity_key},
                tax_period=case.tax_period,
                evidence_claim_ids=[evidence.id],
                status="PENDING_REVIEW",
                source="DOCUMENT",
                idempotency_key=idempotency,
                proposed_by=actor.user_id,
                model_explanation=f"Extracted by {adapter.code} {adapter.version}",
            )
            db.add(candidate)
            candidates.append(candidate)
        run.status = "COMPLETED"
        run.metrics = {**result.metadata, "claim_count": len(result.claims), "warnings": result.warnings}
        run.completed_at = datetime.now(timezone.utc)
        document.document_type = result.document_type
        document.state = "VALIDATION_REQUIRED"
        document.classification_confidence = score
        document.classification_metadata = {**document.classification_metadata, "adapter": adapter.code, "adapter_version": adapter.version, "warnings": result.warnings}
        db.flush()
        append_audit(db, actor=actor, action="document.extracted", entity_type="document", entity_id=document.id, case_id=document.case_id, after={"adapter": adapter.code, "claims": len(result.claims), "warnings": result.warnings})
        # Refresh cross-document reconciliation now that a new source was added.
        safe_rebuild(db, actor, document.case_id)
        return document, run, candidates
    except Exception as exc:
        run.status = "FAILED"
        run.error_message = str(exc)[:4000]
        run.completed_at = datetime.now(timezone.utc)
        document.state = "PARSER_FAILED"
        db.flush()
        # Return a clear error with context for debugging
        import traceback
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Document extraction failed: {str(exc)}",
                "adapter": adapter.code,
                "document_id": document_id,
                "hint": "Check Render logs for full traceback. Common issues: openpyxl not installed, Vision API not configured, or malformed PDF."
            }
        ) from exc


def unlock_document(db: Session, *, actor: Actor, document_id: str, password: str) -> Document:
    """Unlock a password-protected document: decrypt the stored file in place,
    clear the locked state, and remember the password for the case so sibling
    documents auto-unlock. Downstream reads then need no password.
    """
    document = db.scalar(select(Document).where(Document.id == document_id, Document.tenant_id == actor.tenant_id))
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    case = assert_case_access(db, actor, document.case_id, "document:*")
    assert_case_mutable(case)
    data = storage.get(document.storage_key)
    if not is_encrypted(data):
        document.state = "SECURITY_CHECKED"
        document.is_password_protected = False
        db.flush()
        return document
    unlocked = unlock_pdf(data, password)
    if unlocked is None:
        raise HTTPException(status_code=400, detail="Incorrect password for this document.")
    storage.put(key=document.storage_key, data=unlocked, content_type=document.mime_type, metadata={"tenant_id": actor.tenant_id, "case_id": document.case_id})
    document.state = "SECURITY_CHECKED"
    document.is_password_protected = False
    remember_password(db, actor, document.case_id, password)
    append_audit(db, actor=actor, action="document.unlocked", entity_type="document", entity_id=document.id, case_id=document.case_id, after={"filename": document.original_filename})
    db.flush()
    return document
