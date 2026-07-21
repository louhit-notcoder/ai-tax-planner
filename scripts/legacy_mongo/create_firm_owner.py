#!/usr/bin/env python3
"""Provision or promote a firm owner from a verified OAuth account."""
from __future__ import annotations

import argparse
import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient


async def main(email: str, tenant_id: str):
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "green_papaya")]
    result = await db.users.update_one(
        {"email": email.lower()},
        {"$set": {"role": "firm_owner", "tenant_id": tenant_id}},
    )
    if result.matched_count != 1:
        raise SystemExit("No verified user exists with that email. Ask the user to sign in once first.")
    print(f"Provisioned {email.lower()} as firm_owner in {tenant_id}")
    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument("tenant_id", help="Example: firm:acme-ca")
    args = parser.parse_args()
    asyncio.run(main(args.email, args.tenant_id))
