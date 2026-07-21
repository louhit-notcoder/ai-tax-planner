from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import append_audit
from ..database import get_db
from ..communications import CommunicationDeliveryError, send_member_invitation
from ..config import get_settings
from ..db_models import FeatureFlag, Invitation, Membership, Tenant, User
from ..security import Actor, get_actor, require_permission, token_digest
from .schemas import FeatureFlagUpdate, InvitationRequest

router = APIRouter(prefix="/tenant", tags=["tenant"])


@router.get("")
def get_tenant(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    tenant = db.get(Tenant, actor.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"id": tenant.id, "name": tenant.name, "slug": tenant.slug, "status": tenant.status, "sole_practitioner_mode": tenant.sole_practitioner_mode, "settings": tenant.settings}


@router.get("/members")
def list_members(actor: Actor = Depends(require_permission("member:read")), db: Session = Depends(get_db)):
    rows = db.execute(select(Membership, User).join(User, Membership.user_id == User.id).where(Membership.tenant_id == actor.tenant_id)).all()
    return [{"membership_id": membership.id, "user_id": user.id, "email": user.email, "full_name": user.full_name, "role": membership.role, "status": membership.status, "mfa_enabled": user.mfa_enabled} for membership, user in rows]


@router.post("/invitations", status_code=201)
def invite(payload: InvitationRequest, actor: Actor = Depends(require_permission("member:invite")), db: Session = Depends(get_db)):
    raw = secrets.token_urlsafe(48)
    invitation = Invitation(
        tenant_id=actor.tenant_id,
        email=str(payload.email).lower(),
        role=payload.role,
        token_hash=token_digest(raw),
        invited_by=actor.user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=payload.expires_days),
    )
    db.add(invitation); db.flush()
    settings = get_settings()
    delivery = "RETURNED_FOR_DEVELOPMENT_ONLY"
    if settings.is_production:
        tenant = db.get(Tenant, actor.tenant_id)
        try:
            send_member_invitation(recipient=invitation.email, firm_name=tenant.name if tenant else "your CA firm", role=invitation.role, token=raw)
        except CommunicationDeliveryError as exc:
            db.rollback()
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        delivery = "SMTP_SENT"
    append_audit(db, actor=actor, action="member.invited", entity_type="invitation", entity_id=invitation.id, after={"email": invitation.email, "role": invitation.role, "expires_at": invitation.expires_at, "delivery": delivery})
    db.commit()
    result = {"invitation_id": invitation.id, "expires_at": invitation.expires_at, "delivery": delivery}
    if not settings.is_production:
        result["token"] = raw
    return result


@router.get("/feature-flags")
def flags(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    rows = list(db.scalars(select(FeatureFlag).where((FeatureFlag.tenant_id == actor.tenant_id) | (FeatureFlag.tenant_id.is_(None)))))
    return [{"key": row.flag_key, "enabled": row.enabled, "config": row.config_json, "scope": "tenant" if row.tenant_id else "global"} for row in rows]


@router.put("/feature-flags/{flag_key}")
def update_flag(flag_key: str, payload: FeatureFlagUpdate, actor: Actor = Depends(require_permission("tenant:read")), db: Session = Depends(get_db)):
    if actor.role not in {"firm_owner", "ca_partner"}:
        raise HTTPException(status_code=403, detail="Only firm owner or partner can change feature flags")
    row = db.scalar(select(FeatureFlag).where(FeatureFlag.tenant_id == actor.tenant_id, FeatureFlag.flag_key == flag_key))
    if not row:
        row = FeatureFlag(tenant_id=actor.tenant_id, flag_key=flag_key)
        db.add(row)
    row.enabled = payload.enabled
    row.config_json = payload.config
    row.changed_by = actor.user_id
    append_audit(db, actor=actor, action="feature_flag.updated", entity_type="feature_flag", entity_id=flag_key, after={"enabled": payload.enabled, "config": payload.config})
    db.commit()
    return {"key": flag_key, "enabled": row.enabled, "config": row.config_json}
