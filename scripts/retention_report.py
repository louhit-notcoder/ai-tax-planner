#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import argparse
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select

from app.database import SessionLocal
from app.db_models import Document, TaxCase


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run retention inventory; never deletes records")
    parser.add_argument("--days", type=int, default=2555)
    args = parser.parse_args()
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    with SessionLocal() as db:
        case_count = db.scalar(select(func.count()).select_from(TaxCase).where(TaxCase.updated_at < cutoff)) or 0
        document_count = db.scalar(select(func.count()).select_from(Document).join(TaxCase, Document.case_id == TaxCase.id).where(TaxCase.updated_at < cutoff)) or 0
    print({"mode": "DRY_RUN_ONLY", "cutoff": cutoff.isoformat(), "cases": case_count, "documents": document_count, "note": "Apply legal holds and approved tenant retention policies before deletion."})


if __name__ == "__main__":
    main()
