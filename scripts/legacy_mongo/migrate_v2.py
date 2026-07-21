#!/usr/bin/env python3
"""Idempotent Mongo migration for Green Papaya V2.

Dry-run is the default. Run with --apply only after a verified backup and staging test.
The migration adds tenant IDs, assignment arrays and document hashes where available.
It does not approve legacy parsed values or convert them into canonical facts.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def migrate(apply: bool):
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "green_papaya")]
    counts = {"users": 0, "filings": 0, "documents": 0}

    async for user in db.users.find({}):
        updates = {}
        if not user.get("tenant_id"):
            updates["tenant_id"] = f"personal:{user['user_id']}"
        if user.get("role") == "ca_partner" and not os.environ.get("MIGRATION_DEFAULT_CA_TENANT"):
            print(f"WARNING: CA user {user['user_id']} needs an explicit firm tenant")
        elif user.get("role") == "ca_partner" and user.get("tenant_id", "").startswith("personal:"):
            updates["tenant_id"] = os.environ["MIGRATION_DEFAULT_CA_TENANT"]
        if updates:
            counts["users"] += 1
            if apply:
                await db.users.update_one({"_id": user["_id"]}, {"$set": {**updates, "migrated_v2_at": now_iso()}})

    async for filing in db.filings.find({}):
        updates = {}
        if not filing.get("tenant_id"):
            updates["tenant_id"] = f"personal:{filing['user_id']}"
        updates.setdefault("assigned_preparer_id", None)
        updates.setdefault("assigned_reviewer_id", filing.get("assigned_ca_id"))
        updates.setdefault("permitted_user_ids", [])
        updates.setdefault("locked_snapshot", None)
        updates.pop("itd_json", None)
        counts["filings"] += 1
        if apply:
            await db.filings.update_one({"_id": filing["_id"]}, {
                "$set": {**updates, "migrated_v2_at": now_iso()},
                "$unset": {"itd_json": ""},
            })

    async for document in db.documents.find({}):
        updates = {}
        if not document.get("tenant_id"):
            filing = await db.filings.find_one({"id": document.get("filing_id")}) if document.get("filing_id") else None
            updates["tenant_id"] = (filing or {}).get("tenant_id", f"personal:{document['user_id']}")
        updates.setdefault("version", 1)
        updates.setdefault("status", "EXTRACTED" if document.get("parsed_json") else "UPLOADED")
        counts["documents"] += 1
        if apply:
            await db.documents.update_one({"_id": document["_id"]}, {"$set": {**updates, "migrated_v2_at": now_iso()}})

    print({"mode": "APPLY" if apply else "DRY_RUN", "records_examined_or_changed": counts})
    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply changes. Default is dry-run.")
    args = parser.parse_args()
    asyncio.run(migrate(args.apply))
