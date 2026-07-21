#!/usr/bin/env python3
"""Conservative legacy importer.

This script imports legacy clients/cases/documents into PostgreSQL. Legacy parsed values
are never approved. They are imported as untrusted metadata for a CA to re-extract and
review. Run first with --dry-run against a database backup.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import argparse
import os
from pymongo import MongoClient
from sqlalchemy import select

from app.database import SessionLocal, create_all
from app.db_models import Client, Document, Membership, TaxCase, Tenant, User
from app.security import blind_index, encrypt_text, hash_password


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mongo-url", default=os.getenv("LEGACY_MONGO_URL", "mongodb://localhost:27017"))
    parser.add_argument("--mongo-db", default=os.getenv("LEGACY_MONGO_DB", "green_papaya"))
    parser.add_argument("--tenant-slug", required=True)
    parser.add_argument("--tenant-name", required=True)
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--owner-name", default="Migration Owner")
    parser.add_argument("--owner-password", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    source = MongoClient(args.mongo_url)[args.mongo_db]
    inventory = {name: source[name].count_documents({}) for name in ["users", "filings", "documents"]}
    print({"source_inventory": inventory, "mode": "APPLY" if args.apply else "DRY_RUN"})
    if not args.apply:
        return

    create_all()
    with SessionLocal() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == args.tenant_slug)) or Tenant(name=args.tenant_name, slug=args.tenant_slug)
        db.add(tenant); db.flush()
        owner = db.scalar(select(User).where(User.email == args.owner_email.lower())) or User(email=args.owner_email.lower(), full_name=args.owner_name, password_hash=hash_password(args.owner_password))
        db.add(owner); db.flush()
        if not db.scalar(select(Membership).where(Membership.tenant_id == tenant.id, Membership.user_id == owner.id)):
            db.add(Membership(tenant_id=tenant.id, user_id=owner.id, role="firm_owner"))
        db.flush()
        client_map = {}
        for filing in source.filings.find({}):
            legacy_user_id = str(filing.get("user_id") or filing.get("client_id") or filing.get("_id"))
            client = client_map.get(legacy_user_id)
            if not client:
                legacy_user = source.users.find_one({"user_id": filing.get("user_id")}) or {}
                pan = legacy_user.get("pan") or filing.get("pan")
                client = Client(
                    tenant_id=tenant.id,
                    display_name=legacy_user.get("name") or filing.get("client_name") or f"Legacy client {legacy_user_id[-8:]}",
                    email=legacy_user.get("email"),
                    pan_encrypted=encrypt_text(pan) if pan else None,
                    pan_blind_index=blind_index(pan) if pan else None,
                    metadata_json={"legacy_user_id": legacy_user_id, "migration_source": "mongo", "requires_identity_review": True},
                )
                db.add(client); db.flush(); client_map[legacy_user_id] = client
            tax_period = filing.get("financial_year") or filing.get("tax_period") or "FY_2025_26"
            case = db.scalar(select(TaxCase).where(TaxCase.tenant_id == tenant.id, TaxCase.client_id == client.id, TaxCase.tax_period == tax_period))
            if not case:
                case = TaxCase(tenant_id=tenant.id, client_id=client.id, tax_period=tax_period, assessment_year=filing.get("assessment_year") or "AY_2026_27", status="MIGRATED_REVIEW_REQUIRED", preparer_id=owner.id, reviewer_id=owner.id, risk_flags=["LEGACY_IMPORT_REQUIRES_REEXTRACTION"])
                db.add(case); db.flush()
            for legacy_doc in source.documents.find({"filing_id": filing.get("filing_id") or filing.get("id")}):
                sha = legacy_doc.get("sha256")
                if not sha:
                    continue
                if db.scalar(select(Document).where(Document.tenant_id == tenant.id, Document.case_id == case.id, Document.sha256 == sha)):
                    continue
                db.add(Document(tenant_id=tenant.id, case_id=case.id, uploaded_by=owner.id, document_type=legacy_doc.get("doc_type") or "LEGACY_UNKNOWN", state="MIGRATED_REUPLOAD_REQUIRED", original_filename=legacy_doc.get("filename") or "legacy-document", mime_type=legacy_doc.get("mime_type") or "application/octet-stream", size_bytes=int(legacy_doc.get("size_bytes") or 0), sha256=sha, storage_key=legacy_doc.get("storage_path") or "legacy://unavailable", classification_metadata={"legacy_document_id": str(legacy_doc.get("_id")), "parsed_values_not_imported": True}))
        db.commit()
        print({"tenant_id": tenant.id, "clients": len(client_map), "status": "IMPORTED_FOR_REVIEW"})


if __name__ == "__main__":
    main()
