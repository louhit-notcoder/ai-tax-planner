#!/usr/bin/env python3
"""Dry-run-first retention report.

Deletion is intentionally not implemented until the firm's approved retention policy,
legal holds, and client notification process are configured.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient


async def main(days: int):
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "green_papaya")]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    query = {"locked": True, "updated_at": {"$lt": cutoff}, "legal_hold": {"$ne": True}}
    count = await db.filings.count_documents(query)
    print({"mode": "DRY_RUN_ONLY", "cutoff": cutoff, "eligible_cases": count})
    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=2555)
    args = parser.parse_args()
    asyncio.run(main(args.days))
