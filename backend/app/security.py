from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .db_models import CaseAccess, Membership, RefreshSession, TaxCase, User

PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "firm_owner": frozenset({"*"}),
    "ca_partner": frozenset({
        "tenant:read", "member:read", "member:invite", "client:*", "case:*", "document:*",
        "fact:*", "computation:*", "review:*", "export:*", "assistant:*", "audit:read", "privacy:*",
    }),
    "ca_manager": frozenset({
        "tenant:read", "member:read", "client:*", "case:*", "document:*", "fact:*",
        "computation:*", "review:*", "export:*", "assistant:*", "audit:read",
    }),
    "preparer": frozenset({
        "client:read", "client:create", "case:read", "case:create", "case:update", "document:*",
        "fact:read", "fact:propose", "fact:review_low_risk", "computation:run", "computation:read",
        "assistant:*", "reconciliation:*", "export:prepare",
    }),
    "document_operator": frozenset({
        "client:read", "case:read", "document:*", "fact:read", "fact:propose", "assistant:read",
    }),
    "auditor": frozenset({
        "client:read", "case:read", "document:read", "fact:read", "computation:read", "export:read", "audit:read",
    }),
    "client_portal": frozenset({"case:read_own", "document:upload_own", "question:answer_own", "privacy:create_own"}),
}

PRIVILEGED_ROLES = {"firm_owner", "ca_partner", "ca_manager", "preparer", "document_operator", "auditor"}


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except Exception:
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def encrypt_text(value: str) -> str:
    settings = get_settings()
    key = bytes.fromhex(settings.encryption_key_hex)
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(key).encrypt(nonce, value.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_text(value: str) -> str:
    settings = get_settings()
    raw = base64.urlsafe_b64decode(value.encode("ascii"))
    return AESGCM(bytes.fromhex(settings.encryption_key_hex)).decrypt(raw[:12], raw[12:], None).decode("utf-8")


def blind_index(value: str) -> str:
    secret = get_settings().blind_index_secret.encode("utf-8")
    normalized = "".join(value.upper().split())
    return hmac.new(secret, normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def create_access_token(*, user_id: str, tenant_id: str, role: str, mfa: bool) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "mfa": mfa,
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        "jti": secrets.token_hex(16),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], issuer=settings.jwt_issuer)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token") from exc
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    return payload


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _totp_code(secret: str, at_time: int | None = None, step: int = 30, digits: int = 6) -> str:
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    counter = int((at_time or time.time()) // step)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(value).zfill(digits)


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    now = int(time.time())
    return any(hmac.compare_digest(_totp_code(secret, now + delta * 30), code) for delta in range(-window, window + 1))


def permission_matches(granted: str, required: str) -> bool:
    if granted == "*" or granted == required:
        return True
    if granted.endswith(":*") and required.startswith(granted[:-1]):
        return True
    return False


def has_permission(role: str, required: str) -> bool:
    return any(permission_matches(item, required) for item in ROLE_PERMISSIONS.get(role, frozenset()))


@dataclass(frozen=True)
class Actor:
    user_id: str
    tenant_id: str
    role: str
    mfa_verified: bool
    permissions: frozenset[str]


async def get_actor(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Actor:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        token = request.cookies.get("gp_access")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_access_token(token)
    user = db.scalar(select(User).where(User.id == payload["sub"], User.status == "ACTIVE"))
    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == payload["sub"],
            Membership.tenant_id == payload["tenant_id"],
            Membership.status == "ACTIVE",
        )
    )
    if not user or not membership or membership.role != payload.get("role"):
        raise HTTPException(status_code=401, detail="Session membership is no longer valid")
    if get_settings().require_mfa_for_privileged_roles and membership.role in PRIVILEGED_ROLES:
        if not user.mfa_enabled:
            raise HTTPException(status_code=403, detail="MFA enrollment required")
        if not payload.get("mfa"):
            raise HTTPException(status_code=403, detail="MFA verification required")
    return Actor(
        user_id=user.id,
        tenant_id=membership.tenant_id,
        role=membership.role,
        mfa_verified=bool(payload.get("mfa")),
        permissions=ROLE_PERMISSIONS.get(membership.role, frozenset()),
    )



async def get_actor_allow_mfa_setup(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Actor:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        token = request.cookies.get("gp_access")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_access_token(token)
    user = db.scalar(select(User).where(User.id == payload["sub"], User.status == "ACTIVE"))
    membership = db.scalar(select(Membership).where(Membership.user_id == payload["sub"], Membership.tenant_id == payload["tenant_id"], Membership.status == "ACTIVE"))
    if not user or not membership or membership.role != payload.get("role"):
        raise HTTPException(status_code=401, detail="Session membership is no longer valid")
    return Actor(user.id, membership.tenant_id, membership.role, bool(payload.get("mfa")), ROLE_PERMISSIONS.get(membership.role, frozenset()))

def require_permission(permission: str):
    async def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        if not has_permission(actor.role, permission):
            raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
        return actor

    return dependency


def assert_case_access(db: Session, actor: Actor, case_id: str, required: str = "case:read") -> TaxCase:
    if not has_permission(actor.role, required):
        raise HTTPException(status_code=403, detail=f"Permission denied: {required}")
    case = db.scalar(select(TaxCase).where(TaxCase.id == case_id, TaxCase.tenant_id == actor.tenant_id))
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    broad_roles = {"firm_owner", "ca_partner", "ca_manager", "auditor"}
    if actor.role not in broad_roles:
        assigned = actor.user_id in {case.preparer_id, case.reviewer_id}
        explicit = db.scalar(select(CaseAccess).where(CaseAccess.case_id == case.id, CaseAccess.user_id == actor.user_id))
        if not assigned and not explicit:
            raise HTTPException(status_code=403, detail="You are not assigned to this case")
    return case


def assert_case_mutable(case: TaxCase) -> None:
    if case.locked_at is not None:
        raise HTTPException(status_code=409, detail="Case is locked; create an amendment or unlock through reviewer workflow")


def create_refresh_session(
    db: Session,
    *,
    user_id: str,
    tenant_id: str,
    ip_address: str | None,
    user_agent: str | None,
    mfa_verified: bool = False,
) -> tuple[RefreshSession, str]:
    token = create_refresh_token()
    session = RefreshSession(
        user_id=user_id,
        tenant_id=tenant_id,
        token_hash=token_digest(token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=get_settings().refresh_token_days),
        ip_address=ip_address,
        user_agent=user_agent,
        mfa_verified=mfa_verified,
    )
    db.add(session)
    db.flush()
    return session, token


def stable_json_hash(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
