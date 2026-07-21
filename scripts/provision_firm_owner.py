#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import argparse
from sqlalchemy import select

from app.database import SessionLocal, create_all
from app.db_models import Membership, Tenant, User
from app.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first firm owner in PostgreSQL")
    parser.add_argument("--firm", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    create_all()
    with SessionLocal() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == args.slug))
        if not tenant:
            tenant = Tenant(name=args.firm, slug=args.slug)
            db.add(tenant); db.flush()
        user = db.scalar(select(User).where(User.email == args.email.lower()))
        if not user:
            user = User(email=args.email.lower(), full_name=args.name, password_hash=hash_password(args.password))
            db.add(user); db.flush()
        membership = db.scalar(select(Membership).where(Membership.tenant_id == tenant.id, Membership.user_id == user.id))
        if not membership:
            membership = Membership(tenant_id=tenant.id, user_id=user.id, role="firm_owner")
            db.add(membership)
        else:
            membership.role = "firm_owner"; membership.status = "ACTIVE"
        db.commit()
        print({"tenant_id": tenant.id, "user_id": user.id, "email": user.email, "mfa_next": True})


if __name__ == "__main__":
    main()
