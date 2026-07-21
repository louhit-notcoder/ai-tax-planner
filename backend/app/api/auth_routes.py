from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import append_audit
from ..config import get_settings
from ..database import get_db
from ..db_models import Invitation, Membership, RefreshSession, Tenant, User
from ..security import (
    Actor,
    create_access_token,
    create_refresh_session,
    decrypt_text,
    encrypt_text,
    generate_totp_secret,
    get_actor,
    get_actor_allow_mfa_setup,
    hash_password,
    token_digest,
    verify_password,
    verify_totp,
)
from .schemas import AcceptInvitationRequest, BootstrapRequest, LoginRequest, MFAConfirmRequest, RefreshRequest

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(db: Session, user: User, membership: Membership, request: Request, response: Response, *, mfa: bool):
    access = create_access_token(user_id=user.id, tenant_id=membership.tenant_id, role=membership.role, mfa=mfa)
    session, refresh = create_refresh_session(db, user_id=user.id, tenant_id=membership.tenant_id, ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"), mfa_verified=mfa)
    user.last_login_at = datetime.now(timezone.utc)
    settings = get_settings()
    cookie_options = {
        "httponly": True,
        "secure": settings.is_production,
        "samesite": "lax",
    }
    response.set_cookie("gp_access", access, max_age=settings.access_token_minutes * 60, path="/", **cookie_options)
    response.set_cookie("gp_refresh", refresh, max_age=settings.refresh_token_days * 86400, path="/api/auth", **cookie_options)
    result = {
        "token_type": "cookie",
        "expires_in": get_settings().access_token_minutes * 60,
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "tenant_id": membership.tenant_id, "role": membership.role, "mfa_enabled": user.mfa_enabled, "mfa_verified": mfa},
    }
    if settings.expose_auth_tokens_in_response:
        result.update({"access_token": access, "refresh_token": refresh, "token_type": "bearer"})
    return result


def _is_expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value < datetime.now(timezone.utc)


@router.post("/bootstrap", status_code=201)
def bootstrap(payload: BootstrapRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.allow_dev_bootstrap:
        raise HTTPException(status_code=403, detail="Bootstrap is disabled")
    if db.scalar(select(Tenant.id).limit(1)):
        raise HTTPException(status_code=409, detail="A tenant already exists; use the invitation workflow")
    tenant = Tenant(name=payload.firm_name, slug=payload.firm_slug, status="ACTIVE")
    user = User(email=str(payload.owner_email).lower(), full_name=payload.owner_name, password_hash=hash_password(payload.password), status="ACTIVE")
    db.add_all([tenant, user]); db.flush()
    membership = Membership(tenant_id=tenant.id, user_id=user.id, role="firm_owner", status="ACTIVE")
    db.add(membership); db.flush()
    actor = Actor(user.id, tenant.id, "firm_owner", False, frozenset({"*"}))
    append_audit(db, actor=actor, action="tenant.bootstrapped", entity_type="tenant", entity_id=tenant.id, after={"name": tenant.name, "slug": tenant.slug})
    result = _token_response(db, user, membership, request, response, mfa=True)
    db.commit()
    return result


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(payload.email).lower(), User.status == "ACTIVE"))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    memberships = list(db.scalars(select(Membership).join(Tenant, Membership.tenant_id == Tenant.id).where(Membership.user_id == user.id, Membership.status == "ACTIVE", Tenant.status == "ACTIVE")))
    if payload.tenant_slug:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == payload.tenant_slug, Tenant.status == "ACTIVE"))
        membership = next((item for item in memberships if tenant and item.tenant_id == tenant.id), None)
    elif len(memberships) == 1:
        membership = memberships[0]
    else:
        return {"tenant_selection_required": True, "tenants": [{"tenant_id": item.tenant_id, "role": item.role} for item in memberships]}
    if not membership:
        raise HTTPException(status_code=403, detail="No active membership for selected tenant")
    mfa_ok = False
    if user.mfa_enabled:
        if not payload.totp_code or not user.mfa_secret_encrypted or not verify_totp(decrypt_text(user.mfa_secret_encrypted), payload.totp_code):
            raise HTTPException(status_code=401, detail="Valid MFA code required")
        mfa_ok = True
    result = _token_response(db, user, membership, request, response, mfa=mfa_ok)
    db.commit()
    return result


@router.post("/refresh")
def refresh(request: Request, response: Response, payload: RefreshRequest | None = None, db: Session = Depends(get_db)):
    raw_refresh = (payload.refresh_token if payload else None) or request.cookies.get("gp_refresh")
    if not raw_refresh:
        raise HTTPException(status_code=401, detail="Refresh token is required")
    session = db.scalar(select(RefreshSession).where(RefreshSession.token_hash == token_digest(raw_refresh), RefreshSession.revoked_at.is_(None)))
    if not session or _is_expired(session.expires_at):
        raise HTTPException(status_code=401, detail="Refresh token is invalid or expired")
    user = db.get(User, session.user_id)
    membership = db.scalar(select(Membership).where(Membership.user_id == session.user_id, Membership.tenant_id == session.tenant_id, Membership.status == "ACTIVE"))
    if not user or not membership:
        raise HTTPException(status_code=401, detail="Session is no longer valid")
    session.revoked_at = datetime.now(timezone.utc)
    if user.mfa_enabled and not session.mfa_verified:
        raise HTTPException(status_code=401, detail="Fresh MFA verification required")
    result = _token_response(db, user, membership, request, response, mfa=session.mfa_verified)
    db.commit()
    return result


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, payload: RefreshRequest | None = None, db: Session = Depends(get_db)):
    raw_refresh = (payload.refresh_token if payload else None) or request.cookies.get("gp_refresh")
    session = db.scalar(select(RefreshSession).where(RefreshSession.token_hash == token_digest(raw_refresh))) if raw_refresh else None
    if session:
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()
    response.delete_cookie("gp_access", path="/")
    response.delete_cookie("gp_refresh", path="/api/auth")
    response.status_code = 204
    return response


@router.get("/me")
def me(actor: Actor = Depends(get_actor_allow_mfa_setup), db: Session = Depends(get_db)):
    user = db.get(User, actor.user_id)
    return {"id": actor.user_id, "user_id": actor.user_id, "email": user.email if user else None, "full_name": user.full_name if user else None, "tenant_id": actor.tenant_id, "role": actor.role, "mfa_enabled": bool(user and user.mfa_enabled), "mfa_verified": actor.mfa_verified, "permissions": sorted(actor.permissions)}


@router.post("/mfa/setup")
def mfa_setup(actor: Actor = Depends(get_actor_allow_mfa_setup), db: Session = Depends(get_db)):
    user = db.get(User, actor.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    secret = generate_totp_secret()
    user.mfa_secret_encrypted = encrypt_text(secret)
    user.mfa_enabled = False
    db.commit()
    return {"secret": secret, "otpauth_uri": f"otpauth://totp/GreenPapaya:{user.email}?secret={secret}&issuer=GreenPapaya"}


@router.post("/mfa/confirm")
def mfa_confirm(payload: MFAConfirmRequest, request: Request, response: Response, actor: Actor = Depends(get_actor_allow_mfa_setup), db: Session = Depends(get_db)):
    user = db.get(User, actor.user_id)
    membership = db.scalar(select(Membership).where(Membership.user_id == actor.user_id, Membership.tenant_id == actor.tenant_id, Membership.status == "ACTIVE"))
    if not user or not membership or not user.mfa_secret_encrypted:
        raise HTTPException(status_code=409, detail="MFA setup has not been started")
    if not verify_totp(decrypt_text(user.mfa_secret_encrypted), payload.code):
        raise HTTPException(status_code=400, detail="Invalid MFA code")
    user.mfa_enabled = True
    result = _token_response(db, user, membership, request, response, mfa=True)
    db.commit()
    return result


@router.post("/invitations/accept", status_code=201)
def accept_invitation(payload: AcceptInvitationRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == token_digest(payload.token), Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None)))
    if not invitation or _is_expired(invitation.expires_at):
        raise HTTPException(status_code=400, detail="Invitation is invalid or expired")
    user = db.scalar(select(User).where(User.email == invitation.email.lower()))
    if not user:
        user = User(email=invitation.email.lower(), full_name=payload.full_name, password_hash=hash_password(payload.password), status="ACTIVE")
        db.add(user); db.flush()
    elif not user.password_hash:
        user.password_hash = hash_password(payload.password)
    membership = db.scalar(select(Membership).where(Membership.tenant_id == invitation.tenant_id, Membership.user_id == user.id))
    if not membership:
        membership = Membership(tenant_id=invitation.tenant_id, user_id=user.id, role=invitation.role, status="ACTIVE")
        db.add(membership); db.flush()
    invitation.accepted_at = datetime.now(timezone.utc)
    result = _token_response(db, user, membership, request, response, mfa=False)
    db.commit()
    return result
