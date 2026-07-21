from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import Response as FastResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from crypto_vault import vault
import ais_decryptor
import parser as docparser
import storage as store
from parser import parse_document
from pdf_report import build_computation_pdf
from tax_engine import CapitalGainsInput, TaxComputeRequest, engine
from production.assistant_tools import AssistantToolGateway
from production.audit import append_audit_event
from production.document_security import inspect_upload
from production.facts import (
    create_extraction_claims,
    list_current_canonical_facts,
    review_candidate_fact,
)
from production.form_eligibility import determine_form
from production.hashing import sha256_json
from production.itr_export import ExportBlockedError, build_internal_audit_export, build_official_itr_export
from production.legal_sources import search_tax_law
from production.missing_info import list_missing_information
from production.models import (
    AssistantToolCall,
    CA_ROLES,
    CandidateFactReview,
    ToolExecutionContext,
)
from production.security import (
    assert_document_access,
    assert_filing_access,
    permissions_for_role,
    user_tenant_id,
)
from production.snapshots import create_fact_snapshot, snapshot_to_tax_request

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("green-papaya")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "green_papaya")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(
    title="Green Papaya",
    version="2.0.0",
    description="Evidence-linked, deterministic tax preparation foundation. Final filing requires CA approval.",
)
api = APIRouter(prefix="/api")

EMERGENT_SESSION_URL = os.environ.get(
    "EMERGENT_SESSION_URL",
    "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
)
ENVIRONMENT = os.environ.get("GREEN_PAPAYA_ENV", "development").lower()
BOOTSTRAP_CA_EMAILS = {
    email.strip().lower()
    for email in os.environ.get("CA_BOOTSTRAP_EMAILS", "").split(",")
    if email.strip()
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_doc(document: dict) -> dict:
    clean = {key: value for key, value in document.items() if key not in {"_id", "storage_path"}}
    return clean


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class User(StrictModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    role: str = "taxpayer"
    tenant_id: Optional[str] = None
    pan_hash: Optional[str] = None
    created_at: str


class RoleUpdate(StrictModel):
    role: str


class PanUpdate(StrictModel):
    pan: str = Field(pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$")
    dob: Optional[str] = None


class LinkClient(StrictModel):
    client_email: EmailStr


class LinkDecision(StrictModel):
    decision: str = Field(pattern=r"^(ACCEPT|REJECT)$")


class FilingCreate(StrictModel):
    assessment_year: str = "AY 2026-27"


class FilingUpdate(StrictModel):
    selected_regime: Optional[str] = Field(default=None, pattern=r"^(OLD|NEW)$")
    selected_itr_form: Optional[str] = Field(default=None, pattern=r"^ITR-[12]$")
    parsed_payload: Optional[dict] = None


class OverrideRequest(StrictModel):
    state_id: str
    target_field: str
    new_value: float
    justification: str = Field(min_length=8, max_length=2000)


class SessionRequest(StrictModel):
    session_id: str


class LocateReq(StrictModel):
    term: str = Field(min_length=1, max_length=100)


class InvitationCreate(StrictModel):
    email: EmailStr
    role: str = Field(pattern=r"^(ca_partner|ca_manager|preparer|document_operator|auditor)$")


class InvitationAccept(StrictModel):
    token: str = Field(min_length=24, max_length=200)


async def get_current_user(
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> User:
    token = session_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    sess = await db.user_sessions.find_one(
        {"$or": [{"session_token_hash": token_hash(token)}, {"session_token": token}]},
        {"_id": 0},
    )
    if not sess:
        raise HTTPException(status_code=401, detail="Invalid session")
    expires_at = sess["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")

    user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    user.setdefault("tenant_id", f"personal:{user['user_id']}")
    return User(**user)


async def require_ca(user: User = Depends(get_current_user)) -> User:
    if user.role not in CA_ROLES:
        raise HTTPException(status_code=403, detail="CA firm access required")
    return user


async def require_reviewer(user: User = Depends(get_current_user)) -> User:
    if user.role not in {"firm_owner", "ca_partner", "ca_manager"}:
        raise HTTPException(status_code=403, detail="Reviewer access required")
    return user


async def load_filing_or_404(fid: str) -> dict:
    filing = await db.filings.find_one({"id": fid}, {"_id": 0})
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    filing.setdefault("tenant_id", f"personal:{filing.get('user_id')}")
    return filing


async def load_document_or_404(doc_id: str) -> dict:
    document = await db.documents.find_one({"id": doc_id, "is_purged": False}, {"_id": 0})
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


async def filing_for_document(document: dict) -> dict | None:
    if not document.get("filing_id"):
        return None
    return await load_filing_or_404(document["filing_id"])


@api.post("/auth/session")
async def process_session(payload: SessionRequest, response: Response):
    r = requests.get(EMERGENT_SESSION_URL, headers={"X-Session-ID": payload.session_id}, timeout=15)
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session id")
    data = r.json()
    email = data["email"].strip().lower()
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": data.get("name") or existing.get("name"), "picture": data.get("picture")}},
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        is_bootstrap_ca = email in BOOTSTRAP_CA_EMAILS
        role = "ca_partner" if is_bootstrap_ca else "unset"
        tenant_id = "firm:bootstrap" if is_bootstrap_ca else f"personal:{user_id}"
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": data.get("name", email.split("@")[0]),
            "picture": data.get("picture"),
            "role": role,
            "tenant_id": tenant_id,
            "pan_hash": None,
            "created_at": now_iso(),
        })

    raw_token = data.get("session_token") or secrets.token_urlsafe(32)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token_hash": token_hash(raw_token),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": now_iso(),
    })
    response.set_cookie(
        "session_token",
        raw_token,
        httponly=True,
        secure=ENVIRONMENT == "production",
        samesite="lax",
        path="/",
        max_age=7 * 24 * 60 * 60,
    )
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {"user": User(**user), "session_token": raw_token}


@api.get("/auth/me", response_model=User)
async def me(user: User = Depends(get_current_user)):
    return user


@api.post("/auth/logout")
async def logout(
    response: Response,
    session_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
):
    token = session_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if token:
        await db.user_sessions.delete_many({"$or": [{"session_token_hash": token_hash(token)}, {"session_token": token}]})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


@api.post("/auth/role", response_model=User)
async def set_role(payload: RoleUpdate, user: User = Depends(get_current_user)):
    # Privileged roles are invitation-only. New users may only self-select taxpayer.
    if payload.role != "taxpayer":
        raise HTTPException(status_code=403, detail="CA firm roles are invitation-only")
    if user.role not in {"unset", "taxpayer"}:
        raise HTTPException(status_code=409, detail="A privileged role cannot be replaced through self-service")
    await db.users.update_one({"user_id": user.user_id}, {"$set": {"role": "taxpayer"}})
    return User(**await db.users.find_one({"user_id": user.user_id}, {"_id": 0}))


@api.post("/firm/invitations")
async def create_firm_invitation(payload: InvitationCreate, owner: User = Depends(require_reviewer)):
    token = secrets.token_urlsafe(32)
    invitation = {
        "invitation_id": str(uuid.uuid4()),
        "tenant_id": user_tenant_id(owner),
        "email": str(payload.email).lower(),
        "role": payload.role,
        "token_hash": token_hash(token),
        "status": "PENDING",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_by": owner.user_id,
        "created_at": now_iso(),
    }
    await db.firm_invitations.insert_one(invitation.copy())
    result = {key: value for key, value in invitation.items() if key != "token_hash"}
    if ENVIRONMENT != "production":
        result["development_token"] = token
    return result


@api.post("/firm/invitations/accept", response_model=User)
async def accept_firm_invitation(payload: InvitationAccept, user: User = Depends(get_current_user)):
    invitation = await db.firm_invitations.find_one({"token_hash": token_hash(payload.token), "status": "PENDING"}, {"_id": 0})
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation["email"] != user.email.lower():
        raise HTTPException(status_code=403, detail="Invitation belongs to another email address")
    if datetime.fromisoformat(invitation["expires_at"]) < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Invitation expired")
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"role": invitation["role"], "tenant_id": invitation["tenant_id"]}},
    )
    await db.firm_invitations.update_one(
        {"invitation_id": invitation["invitation_id"]},
        {"$set": {"status": "ACCEPTED", "accepted_at": now_iso(), "accepted_by": user.user_id}},
    )
    return User(**await db.users.find_one({"user_id": user.user_id}, {"_id": 0}))


@api.post("/auth/pan", response_model=User)
async def set_pan(payload: PanUpdate, user: User = Depends(get_current_user)):
    pan_hash = vault.blind_hash(payload.pan)
    await db.secure_metadata.update_one(
        {"user_id": user.user_id},
        {"$set": {
            "user_id": user.user_id,
            "tenant_id": user_tenant_id(user),
            "pan_encrypted": vault.encrypt(payload.pan, f"pan:{user.user_id}"),
            "pan_hash": pan_hash,
            "dob_encrypted": vault.encrypt(payload.dob, f"dob:{user.user_id}") if payload.dob else None,
            "key_id": vault.key_id,
            "updated_at": now_iso(),
        }},
        upsert=True,
    )
    await db.users.update_one({"user_id": user.user_id}, {"$set": {"pan_hash": pan_hash}})
    return User(**await db.users.find_one({"user_id": user.user_id}, {"_id": 0}))


@api.post("/tax/compute")
async def compute_tax(req: TaxComputeRequest, user: User = Depends(get_current_user)):
    result = engine.compute(req).model_dump(mode="json")
    result["disclaimer"] = "Calculator output is provisional and is not a filed return."
    return result


@api.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form("unknown"),
    filing_id: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
):
    data = await file.read()
    content_type = file.content_type or "application/octet-stream"
    inspection = inspect_upload(file.filename or "upload.bin", content_type, data)
    filing = None
    if filing_id:
        filing = await load_filing_or_404(filing_id)
        assert_filing_access(user, filing, write=True)
    existing = await db.documents.find_one({
        "tenant_id": user_tenant_id(user),
        "filing_id": filing_id,
        "sha256": inspection.sha256,
        "is_purged": False,
    }, {"_id": 0})
    if existing:
        raise HTTPException(status_code=409, detail="The same file is already attached to this case")

    ext = (file.filename or "upload.bin").rsplit(".", 1)[-1].lower()
    owner_id = filing["user_id"] if filing else user.user_id
    path = f"{store.APP_NAME}/uploads/{user_tenant_id(user)}/{filing_id or owner_id}/{uuid.uuid4().hex}.{ext}"
    result = store.put_object(path, data, content_type)
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": filing.get("tenant_id") if filing else user_tenant_id(user),
        "user_id": owner_id,
        "uploaded_by": user.user_id,
        "document_type": document_type,
        "storage_path": result["path"],
        "file_name": file.filename,
        "content_type": content_type,
        "ext": ext,
        "size": inspection.size,
        "sha256": inspection.sha256,
        "detected_kind": inspection.detected_kind,
        "version": 1,
        "confidence_score": 0.0,
        "parsed_json": None,
        "filing_id": filing_id,
        "status": "UPLOADED",
        "is_purged": False,
        "created_at": now_iso(),
    }
    await db.documents.insert_one(doc.copy())
    await append_audit_event(
        db,
        tenant_id=doc["tenant_id"],
        case_id=filing_id,
        actor_id=user.user_id,
        actor_role=user.role,
        action="DOCUMENT_UPLOADED",
        entity_type="document",
        entity_id=doc["id"],
        after=public_doc(doc),
    )
    return public_doc(doc)


@api.get("/documents")
async def list_documents(user_id: Optional[str] = None, user: User = Depends(get_current_user)):
    if user_id and user_id != user.user_id:
        if user.role not in CA_ROLES:
            raise HTTPException(status_code=403, detail="Access denied")
        accepted_link = await db.ca_clients.find_one({
            "tenant_id": user_tenant_id(user), "ca_id": user.user_id, "client_id": user_id, "status": "ACCEPTED"
        })
        if not accepted_link:
            raise HTTPException(status_code=403, detail="Client is not linked to this CA")
        query = {"tenant_id": user_tenant_id(user), "user_id": user_id, "is_purged": False}
    else:
        query = {"user_id": user.user_id, "is_purged": False}
    docs = await db.documents.find(query, {"_id": 0, "storage_path": 0}).sort("created_at", -1).to_list(500)
    return docs


@api.get("/documents/{doc_id}")
async def get_document(doc_id: str, user: User = Depends(get_current_user)):
    document = await load_document_or_404(doc_id)
    filing = await filing_for_document(document)
    assert_document_access(user, document, filing)
    return public_doc(document)


@api.get("/documents/{doc_id}/download")
async def download_document(doc_id: str, user: User = Depends(get_current_user)):
    document = await load_document_or_404(doc_id)
    filing = await filing_for_document(document)
    assert_document_access(user, document, filing)
    await append_audit_event(
        db,
        tenant_id=document.get("tenant_id") or user_tenant_id(user),
        case_id=document.get("filing_id"),
        actor_id=user.user_id,
        actor_role=user.role,
        action="DOCUMENT_DOWNLOADED",
        entity_type="document",
        entity_id=doc_id,
        metadata={"file_name": document["file_name"]},
    )
    content, ctype = store.get_object(document["storage_path"])
    return FastResponse(
        content=content,
        media_type=document.get("content_type", ctype),
        headers={"Content-Disposition": f'inline; filename="{document["file_name"]}"'},
    )


@api.post("/documents/{doc_id}/parse")
async def parse_doc(doc_id: str, user: User = Depends(get_current_user)):
    document = await load_document_or_404(doc_id)
    filing = await filing_for_document(document)
    if not filing:
        raise HTTPException(status_code=400, detail="Document must be attached to a filing before parsing")
    assert_document_access(user, document, filing, write=True)
    content, _ = store.get_object(document["storage_path"])
    parsed = await parse_document(content, document.get("content_type"), document.get("ext", "pdf"))
    parsed.pop("employee_pan", None)  # Never persist raw PAN in parser output.
    confidence = parsed.get("confidence", 0.0)
    await db.documents.update_one(
        {"id": doc_id},
        {"$set": {"parsed_json": parsed, "confidence_score": confidence, "status": "EXTRACTED", "parsed_at": now_iso()}},
    )
    created = await create_extraction_claims(
        db,
        tenant_id=filing["tenant_id"],
        case_id=filing["id"],
        document=document,
        parsed=parsed,
        actor_id=user.user_id,
    )
    await db.filings.update_one(
        {"id": filing["id"]},
        {"$set": {"status": "under_review", "updated_at": now_iso()}},
    )
    return {
        "parsed_json": parsed,
        "confidence_score": confidence,
        "candidate_facts": created["candidate_facts"],
        "message": "Extraction created reviewable candidate facts. No tax computation was changed.",
    }


@api.get("/documents/{doc_id}/info")
async def document_info(doc_id: str, user: User = Depends(get_current_user)):
    document = await load_document_or_404(doc_id)
    filing = await filing_for_document(document)
    assert_document_access(user, document, filing)
    if not docparser.is_pdf_bytes(document.get("content_type"), document.get("ext")):
        return {"is_pdf": False, "content_type": document.get("content_type")}
    content, _ = store.get_object(document["storage_path"])
    return {**docparser.pdf_info(content), "is_pdf": True}


@api.get("/documents/{doc_id}/page/{page_index}")
async def document_page(doc_id: str, page_index: int, user: User = Depends(get_current_user)):
    document = await load_document_or_404(doc_id)
    filing = await filing_for_document(document)
    assert_document_access(user, document, filing)
    content, _ = store.get_object(document["storage_path"])
    info = docparser.pdf_info(content)
    if page_index < 0 or page_index >= info["page_count"]:
        raise HTTPException(status_code=404, detail="Page not found")
    return FastResponse(content=docparser.render_page_png(content, page_index), media_type="image/png")


@api.post("/documents/{doc_id}/locate")
async def document_locate(doc_id: str, payload: LocateReq, user: User = Depends(get_current_user)):
    document = await load_document_or_404(doc_id)
    filing = await filing_for_document(document)
    assert_document_access(user, document, filing)
    if not docparser.is_pdf_bytes(document.get("content_type"), document.get("ext")):
        return {"page": 0, "rects": [], "matched": None, "evidence_quality": "NOT_AVAILABLE"}
    content, _ = store.get_object(document["storage_path"])
    result = docparser.locate_term(content, payload.term)
    result["evidence_quality"] = "SEARCH_HINT_ONLY"
    result["warning"] = "Text search is not authoritative evidence. Accepted facts use stored evidence claims."
    return result


def legacy_payload_to_request(payload: dict, assessment_year: str = "AY 2026-27") -> TaxComputeRequest:
    return TaxComputeRequest(
        assessment_year=assessment_year,
        gross_salary=payload.get("gross_salary", 0),
        section_10_exemptions=payload.get("section_10_exemptions", 0),
        professional_tax=payload.get("professional_tax", 0),
        deductions_80c=payload.get("deductions_80c", 0),
        deductions_80d=payload.get("deductions_80d", 0),
        other_deductions=payload.get("other_deductions", 0),
        other_income=payload.get("other_income", 0),
        house_property_income=payload.get("house_property_income", 0),
        tds_deducted=payload.get("tds_deducted", 0),
        capital_gains=CapitalGainsInput(
            stcg_equity=payload.get("stcg_equity", 0),
            ltcg_equity=payload.get("ltcg_equity", 0),
            property_sale_price=payload.get("property_sale_price", 0),
            property_purchase_price=payload.get("property_purchase_price", 0),
        ),
        has_business_income=bool(payload.get("has_business_income")),
        has_foreign_assets=bool(payload.get("has_foreign_assets")),
        has_foreign_income=bool(payload.get("has_foreign_income")),
        has_vda_income=bool(payload.get("has_vda_income")),
        has_unlisted_shares=bool(payload.get("has_unlisted_shares")),
    )


def compute_legacy_payload(payload: dict, assessment_year: str = "AY 2026-27") -> dict:
    result = engine.compute(legacy_payload_to_request(payload, assessment_year)).model_dump(mode="json")
    result["computation_status"] = "PROVISIONAL" if result["computation_status"] == "COMPLETE" else result["computation_status"]
    result.setdefault("warnings", []).append({
        "code": "UNAPPROVED_LEGACY_INPUT",
        "message": "This preview uses manually entered or unapproved legacy values and cannot be finalised.",
    })
    return result


@api.post("/filings")
async def create_filing(payload: FilingCreate, user: User = Depends(get_current_user)):
    if payload.assessment_year != "AY 2026-27":
        raise HTTPException(status_code=400, detail="This release supports AY 2026-27 only")
    fid = str(uuid.uuid4())
    document = {
        "id": fid,
        "tenant_id": user_tenant_id(user),
        "user_id": user.user_id,
        "user_name": user.name,
        "user_email": user.email,
        "pan_hash": user.pan_hash,
        "assessment_year": payload.assessment_year,
        "residential_status": "RESIDENT_ORDINARILY_RESIDENT",
        "selected_regime": "NEW",
        "selected_itr_form": None,
        "parsed_payload": {},
        "tax_computation_summary": None,
        "current_computation_run_id": None,
        "reconciliation_discrepancies": [],
        "status": "not_started",
        "assigned_ca_id": None,
        "assigned_preparer_id": None,
        "assigned_reviewer_id": None,
        "permitted_user_ids": [],
        "locked": False,
        "locked_snapshot": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.filings.insert_one(document.copy())
    return document


@api.get("/filings")
async def list_filings(user: User = Depends(get_current_user)):
    if user.role in CA_ROLES:
        query = {
            "tenant_id": user_tenant_id(user),
            "$or": [
                {"assigned_ca_id": user.user_id},
                {"assigned_preparer_id": user.user_id},
                {"assigned_reviewer_id": user.user_id},
                {"permitted_user_ids": user.user_id},
            ],
        }
    else:
        query = {"user_id": user.user_id}
    return await db.filings.find(query, {"_id": 0}).sort("updated_at", -1).to_list(500)


@api.get("/filings/{fid}")
async def get_filing(fid: str, user: User = Depends(get_current_user)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(user, filing)
    return filing


@api.put("/filings/{fid}")
async def update_filing(fid: str, payload: FilingUpdate, user: User = Depends(get_current_user)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(user, filing, write=True)
    update: dict[str, Any] = {"updated_at": now_iso()}
    if payload.selected_regime:
        update["selected_regime"] = payload.selected_regime
    if payload.selected_itr_form:
        update["selected_itr_form"] = payload.selected_itr_form
    merged = dict(filing.get("parsed_payload") or {})
    if payload.parsed_payload is not None:
        allowed = {
            "gross_salary", "section_10_exemptions", "professional_tax", "deductions_80c", "deductions_80d",
            "other_deductions", "other_income", "house_property_income", "stcg_equity", "ltcg_equity", "tds_deducted",
            "has_business_income", "has_foreign_assets", "has_foreign_income", "has_vda_income", "has_unlisted_shares",
        }
        unknown = set(payload.parsed_payload) - allowed
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unsupported input fields: {sorted(unknown)}")
        merged.update(payload.parsed_payload)
        update["parsed_payload"] = merged
    update["tax_computation_summary"] = compute_legacy_payload(merged, filing["assessment_year"])
    update["status"] = "provisional"
    await db.filings.update_one({"id": fid}, {"$set": update})
    return await db.filings.find_one({"id": fid}, {"_id": 0})


@api.post("/filings/{fid}/compute")
async def recompute_preview(fid: str, user: User = Depends(get_current_user)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(user, filing, write=True)
    result = compute_legacy_payload(filing.get("parsed_payload") or {}, filing["assessment_year"])
    await db.filings.update_one({"id": fid}, {"$set": {"tax_computation_summary": result, "status": "provisional", "updated_at": now_iso()}})
    return result


@api.get("/filings/{fid}/facts/candidates")
async def list_candidate_facts(fid: str, user: User = Depends(get_current_user)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(user, filing)
    return await db.candidate_facts.find({"tenant_id": filing["tenant_id"], "case_id": fid}, {"_id": 0}).sort("created_at", -1).to_list(1000)


@api.get("/filings/{fid}/facts")
async def list_canonical_facts(fid: str, user: User = Depends(get_current_user)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(user, filing)
    return await list_current_canonical_facts(db, tenant_id=filing["tenant_id"], case_id=fid)


@api.post("/filings/{fid}/facts/candidates/{candidate_id}/review")
async def review_fact(fid: str, candidate_id: str, payload: CandidateFactReview, reviewer: User = Depends(require_reviewer)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(reviewer, filing, write=True, review=True)
    result = await review_candidate_fact(
        db,
        tenant_id=filing["tenant_id"],
        case_id=fid,
        candidate_fact_id=candidate_id,
        reviewer_id=reviewer.user_id,
        request=payload,
    )
    await append_audit_event(
        db,
        tenant_id=filing["tenant_id"],
        case_id=fid,
        actor_id=reviewer.user_id,
        actor_role=reviewer.role,
        action=f"CANDIDATE_FACT_{payload.decision.value}",
        entity_type="candidate_fact",
        entity_id=candidate_id,
        after=result,
        metadata={"justification": payload.justification},
    )
    return result


@api.get("/filings/{fid}/missing-information")
async def missing_information(fid: str, user: User = Depends(get_current_user)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(user, filing)
    return await list_missing_information(db, tenant_id=filing["tenant_id"], case_id=fid, filing=filing)


@api.post("/filings/{fid}/compute-approved")
async def compute_approved(fid: str, user: User = Depends(get_current_user)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(user, filing, write=True)
    facts = await list_current_canonical_facts(db, tenant_id=filing["tenant_id"], case_id=fid)
    if not facts:
        raise HTTPException(status_code=409, detail="No approved canonical facts are available")
    snapshot = await create_fact_snapshot(
        db,
        tenant_id=filing["tenant_id"],
        case_id=fid,
        created_by=user.user_id,
        rule_release_id=engine.RELEASE_ID,
    )
    mapped = snapshot_to_tax_request(snapshot, filing)
    result_model = engine.compute(TaxComputeRequest.model_validate(mapped["request"]))
    result = result_model.model_dump(mode="json")
    result["facts_used"] = mapped["facts_used"]
    result["facts_not_used"] = mapped["facts_not_used"]
    run = {
        "computation_run_id": str(uuid.uuid4()),
        "tenant_id": filing["tenant_id"],
        "case_id": fid,
        "fact_snapshot_id": snapshot["fact_snapshot_id"],
        "fact_snapshot_hash": snapshot["snapshot_hash"],
        "rule_release_id": result["rule_release_id"],
        "rule_bundle_hash": result["rule_bundle_hash"],
        "result": result,
        "result_hash": result["result_hash"],
        "is_current": True,
        "created_by": user.user_id,
        "created_at": now_iso(),
    }
    await db.computation_runs.update_many(
        {"tenant_id": filing["tenant_id"], "case_id": fid, "is_current": True},
        {"$set": {"is_current": False, "superseded_at": now_iso()}},
    )
    await db.computation_runs.insert_one(run.copy())
    canonical_facts = facts
    form = determine_form(filing=filing, computation=result, canonical_facts=canonical_facts)
    await db.filings.update_one({"id": fid}, {"$set": {
        "current_computation_run_id": run["computation_run_id"],
        "tax_computation_summary": result,
        "form_eligibility": form,
        "selected_itr_form": form["recommended_form"],
        "status": "computed" if result["computation_status"] == "COMPLETE" else "under_review",
        "updated_at": now_iso(),
    }})
    return {"computation_run": run, "form_eligibility": form}


@api.get("/filings/{fid}/computation")
async def current_computation(fid: str, user: User = Depends(get_current_user)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(user, filing)
    run = await db.computation_runs.find_one({"tenant_id": filing["tenant_id"], "case_id": fid, "is_current": True}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail="No approved-fact computation exists")
    return run


@api.post("/filings/{fid}/request-verification")
async def request_verification(fid: str, user: User = Depends(get_current_user)):
    filing = await load_filing_or_404(fid)
    if filing["user_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="Only the taxpayer can request verification")
    link = await db.ca_clients.find_one({"client_id": user.user_id, "status": "ACCEPTED"}, {"_id": 0})
    updates = {"status": "under_review", "updated_at": now_iso()}
    if link:
        updates.update({"tenant_id": link["tenant_id"], "assigned_ca_id": link["ca_id"], "assigned_reviewer_id": link["ca_id"]})
    await db.filings.update_one({"id": fid}, {"$set": updates})
    return await db.filings.find_one({"id": fid}, {"_id": 0})


def run_reconciliation(payload: dict, ais: dict) -> list[dict]:
    flags = []
    checks = [
        ("gross_salary", "HIGH", "Salary"),
        ("tds_deducted", "MEDIUM", "TDS"),
        ("other_income", "MEDIUM", "Other income"),
        ("stcg_equity", "MEDIUM", "Section 111A gain"),
        ("ltcg_equity", "MEDIUM", "Section 112A gain"),
    ]
    for field, severity, label in checks:
        source_value = float(payload.get(field, 0) or 0)
        ais_value = float(ais.get(field, 0) or 0)
        if ais_value and abs(source_value - ais_value) > 100:
            flags.append({
                "reconciliation_item_id": str(uuid.uuid4()),
                "field": field,
                "severity": severity,
                "declared": source_value,
                "ais": ais_value,
                "status": "REVIEW_REQUIRED",
                "message": f"{label} differs: case ₹{source_value:,.0f}, AIS ₹{ais_value:,.0f}.",
            })
    if float(payload.get("deductions_80c", 0) or 0) > 150000:
        flags.append({
            "reconciliation_item_id": str(uuid.uuid4()),
            "field": "deductions_80c",
            "severity": "LOW",
            "declared": payload.get("deductions_80c"),
            "ais": None,
            "status": "REVIEW_REQUIRED",
            "message": "Section 80C exceeds the limited-scope cap of ₹1,50,000.",
        })
    return flags


@api.post("/filings/{fid}/upload-ais")
async def upload_ais(
    fid: str,
    file: UploadFile = File(...),
    pan: str = Form(""),
    dob: str = Form(""),
    password: str = Form(""),
    user: User = Depends(get_current_user),
):
    filing = await load_filing_or_404(fid)
    assert_filing_access(user, filing, write=True)
    raw_bytes = await file.read()
    inspect_upload(file.filename or "ais.json", file.content_type or "application/json", raw_bytes)
    raw = raw_bytes.decode("utf-8", errors="ignore").strip()
    ais_json = None
    try:
        if raw.startswith(("{", "[")):
            ais_json = json.loads(raw)
    except Exception:
        ais_json = None
    if ais_json is None:
        try:
            ais_json = ais_decryptor.decrypt_ais_text(raw, pan, dob, password or None)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"AIS decryption failed: {exc}")
    prefill = ais_decryptor.extract_ais_prefill(ais_json)
    flags = run_reconciliation(filing.get("parsed_payload") or {}, prefill)
    await db.filings.update_one({"id": fid}, {"$set": {
        "ais_prefill": prefill,
        "reconciliation_discrepancies": flags,
        "status": "reconciled" if not flags else "under_review",
        "updated_at": now_iso(),
    }})
    return {"ais_prefill": prefill, "discrepancies": flags, "status": "reconciled" if not flags else "under_review", "amounts_found": prefill.get("_pairs_found", 0)}


@api.post("/filings/{fid}/reconcile")
async def reconcile(fid: str, user: User = Depends(get_current_user)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(user, filing, write=True)
    if not filing.get("ais_prefill"):
        raise HTTPException(status_code=400, detail="No AIS data available")
    flags = run_reconciliation(filing.get("parsed_payload") or {}, filing["ais_prefill"])
    await db.filings.update_one({"id": fid}, {"$set": {"reconciliation_discrepancies": flags, "updated_at": now_iso()}})
    return {"discrepancies": flags, "ais_prefill": filing["ais_prefill"], "status": "reconciled" if not flags else "under_review"}


@api.post("/filings/{fid}/parse-documents")
async def parse_documents_endpoint(fid: str, user: User = Depends(get_current_user)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(user, filing, write=True)
    documents = await db.documents.find({"filing_id": fid, "is_purged": False}, {"_id": 0}).to_list(100)
    if not documents:
        raise HTTPException(status_code=400, detail="No documents attached to this filing")
    outcomes = []
    for document in documents:
        content, _ = store.get_object(document["storage_path"])
        parsed = await parse_document(content, document.get("content_type"), document.get("ext", "pdf"))
        parsed.pop("employee_pan", None)
        await db.documents.update_one({"id": document["id"]}, {"$set": {"parsed_json": parsed, "confidence_score": parsed.get("confidence", 0), "status": "EXTRACTED"}})
        created = await create_extraction_claims(
            db,
            tenant_id=filing["tenant_id"],
            case_id=fid,
            document=document,
            parsed=parsed,
            actor_id=user.user_id,
        )
        outcomes.append({
            "document_id": document["id"],
            "file_name": document["file_name"],
            "parsed_json": parsed,
            "candidate_fact_count": len(created["candidate_facts"]),
        })
    await db.filings.update_one({"id": fid}, {"$set": {"status": "under_review", "updated_at": now_iso()}})
    return {
        "documents_analyzed": len(outcomes),
        "outcomes": outcomes,
        "message": "Documents were parsed independently. Candidate facts require review and were not merged automatically.",
    }


@api.post("/filings/{fid}/form-eligibility/review")
async def approve_form_eligibility(fid: str, reviewer: User = Depends(require_reviewer)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(reviewer, filing, write=True, review=True)
    current = filing.get("form_eligibility")
    if not current:
        raise HTTPException(status_code=409, detail="Run an approved-fact computation first")
    current["status"] = "APPROVED"
    current["approved_by"] = reviewer.user_id
    current["approved_at"] = now_iso()
    await db.filings.update_one({"id": fid}, {"$set": {"form_eligibility": current, "selected_itr_form": current["recommended_form"], "updated_at": now_iso()}})
    return current


@api.post("/filings/{fid}/final-review")
async def final_review(fid: str, reviewer: User = Depends(require_reviewer)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(reviewer, filing, write=True, review=True)
    run = await db.computation_runs.find_one({"tenant_id": filing["tenant_id"], "case_id": fid, "is_current": True}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=409, detail="No approved-fact computation exists")
    if run["result"]["computation_status"] != "COMPLETE":
        raise HTTPException(status_code=409, detail="Computation is not complete")
    pending = await db.candidate_facts.count_documents({"tenant_id": filing["tenant_id"], "case_id": fid, "status": {"$in": ["PENDING_REVIEW", "CONFLICTING"]}})
    if pending:
        raise HTTPException(status_code=409, detail=f"{pending} candidate facts remain unresolved")
    if (filing.get("form_eligibility") or {}).get("status") != "APPROVED":
        raise HTTPException(status_code=409, detail="Form eligibility is not approved")
    approval = {
        "approval_id": str(uuid.uuid4()),
        "tenant_id": filing["tenant_id"],
        "case_id": fid,
        "type": "FINAL_COMPUTATION_REVIEW",
        "computation_run_id": run["computation_run_id"],
        "result_hash": run["result_hash"],
        "approved_by": reviewer.user_id,
        "approved_at": now_iso(),
    }
    await db.approvals.insert_one(approval.copy())
    await db.filings.update_one({"id": fid}, {"$set": {"final_review_approval_id": approval["approval_id"], "status": "approved", "updated_at": now_iso()}})
    return approval


@api.post("/filings/{fid}/lock")
async def lock_filing(fid: str, reviewer: User = Depends(require_reviewer)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(reviewer, filing, write=True, review=True)
    if not filing.get("final_review_approval_id"):
        raise HTTPException(status_code=409, detail="Final review approval is required before locking")
    run = await db.computation_runs.find_one({"tenant_id": filing["tenant_id"], "case_id": fid, "is_current": True}, {"_id": 0})
    snapshot = await db.fact_snapshots.find_one({"fact_snapshot_id": run["fact_snapshot_id"]}, {"_id": 0}) if run else None
    if not run or not snapshot:
        raise HTTPException(status_code=409, detail="Computation snapshot is missing")
    locked_snapshot = {
        "fact_snapshot_id": snapshot["fact_snapshot_id"],
        "fact_snapshot_hash": snapshot["snapshot_hash"],
        "computation_run_id": run["computation_run_id"],
        "result_hash": run["result_hash"],
        "rule_release_id": run["rule_release_id"],
        "rule_bundle_hash": run["rule_bundle_hash"],
        "form_eligibility": filing.get("form_eligibility"),
        "final_review_approval_id": filing["final_review_approval_id"],
        "locked_by": reviewer.user_id,
        "locked_at": now_iso(),
    }
    locked_snapshot["lock_hash"] = sha256_json(locked_snapshot)
    await db.filings.update_one({"id": fid}, {"$set": {"locked": True, "status": "locked", "locked_snapshot": locked_snapshot, "updated_at": now_iso()}})
    return await db.filings.find_one({"id": fid}, {"_id": 0})


@api.get("/filings/{fid}/internal-audit-export")
async def internal_audit_export(fid: str, user: User = Depends(get_current_user)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(user, filing)
    run = await db.computation_runs.find_one({"tenant_id": filing["tenant_id"], "case_id": fid, "is_current": True}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=409, detail="No approved-fact computation exists")
    snapshot = await db.fact_snapshots.find_one({"fact_snapshot_id": run["fact_snapshot_id"]}, {"_id": 0})
    return build_internal_audit_export(
        filing=filing,
        snapshot=snapshot,
        computation=run["result"],
        form_eligibility=filing.get("form_eligibility") or {},
    )


@api.get("/filings/{fid}/export-json")
async def export_json(fid: str, user: User = Depends(get_current_user)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(user, filing)
    try:
        return build_official_itr_export(filing=filing)
    except ExportBlockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@api.get("/filings/{fid}/computation-pdf")
async def computation_pdf(fid: str, user: User = Depends(get_current_user)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(user, filing)
    if not filing.get("tax_computation_summary"):
        raise HTTPException(status_code=409, detail="No computation is available")
    pdf_bytes = build_computation_pdf(filing)
    filename = f"GreenPapaya_Computation_{filing.get('selected_itr_form') or 'DRAFT'}_{fid[:6]}.pdf"
    return FastResponse(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@api.post("/ca/link-client")
async def link_client(payload: LinkClient, ca: User = Depends(require_ca)):
    taxpayer = await db.users.find_one({"email": str(payload.client_email).lower(), "role": {"$in": ["taxpayer", "unset"]}}, {"_id": 0})
    if not taxpayer:
        raise HTTPException(status_code=404, detail="No taxpayer found with that email")
    existing = await db.ca_clients.find_one({"tenant_id": user_tenant_id(ca), "client_id": taxpayer["user_id"], "status": {"$in": ["PENDING", "ACCEPTED"]}}, {"_id": 0})
    if existing:
        return existing
    request_doc = {
        "link_request_id": str(uuid.uuid4()),
        "tenant_id": user_tenant_id(ca),
        "ca_id": ca.user_id,
        "client_id": taxpayer["user_id"],
        "client_email": taxpayer["email"],
        "status": "PENDING",
        "created_at": now_iso(),
    }
    await db.ca_clients.insert_one(request_doc.copy())
    return request_doc


@api.get("/client/ca-link-requests")
async def client_link_requests(user: User = Depends(get_current_user)):
    return await db.ca_clients.find({"client_id": user.user_id, "status": "PENDING"}, {"_id": 0}).to_list(100)


@api.post("/client/ca-link-requests/{request_id}")
async def decide_link_request(request_id: str, payload: LinkDecision, user: User = Depends(get_current_user)):
    link = await db.ca_clients.find_one({"link_request_id": request_id, "client_id": user.user_id, "status": "PENDING"}, {"_id": 0})
    if not link:
        raise HTTPException(status_code=404, detail="Link request not found")
    status = "ACCEPTED" if payload.decision == "ACCEPT" else "REJECTED"
    await db.ca_clients.update_one({"link_request_id": request_id}, {"$set": {"status": status, "decided_at": now_iso()}})
    if status == "ACCEPTED":
        await db.filings.update_many({"user_id": user.user_id, "locked": False}, {"$set": {
            "tenant_id": link["tenant_id"],
            "assigned_ca_id": link["ca_id"],
            "assigned_reviewer_id": link["ca_id"],
            "updated_at": now_iso(),
        }})
        await db.documents.update_many({"user_id": user.user_id, "is_purged": False}, {"$set": {"tenant_id": link["tenant_id"]}})
    return {"status": status}


@api.get("/ca/clients")
async def ca_clients(ca: User = Depends(require_ca)):
    links = await db.ca_clients.find({"tenant_id": user_tenant_id(ca), "ca_id": ca.user_id, "status": "ACCEPTED"}, {"_id": 0}).to_list(500)
    output = []
    for link in links:
        taxpayer = await db.users.find_one({"user_id": link["client_id"]}, {"_id": 0})
        filings = await db.filings.find({"tenant_id": user_tenant_id(ca), "user_id": link["client_id"]}, {"_id": 0}).to_list(100)
        output.append({"client": taxpayer, "filings": filings})
    return output


@api.get("/ca/triage")
async def ca_triage(ca: User = Depends(require_ca)):
    query = {
        "tenant_id": user_tenant_id(ca),
        "$or": [
            {"assigned_ca_id": ca.user_id},
            {"assigned_preparer_id": ca.user_id},
            {"assigned_reviewer_id": ca.user_id},
            {"permitted_user_ids": ca.user_id},
        ],
    }
    return await db.filings.find(query, {"_id": 0}).sort("updated_at", -1).to_list(500)


@api.get("/ca/stats")
async def ca_stats(ca: User = Depends(require_ca)):
    filings = await ca_triage(ca)
    by_status: dict[str, int] = {}
    mismatch_count = 0
    for filing in filings:
        by_status[filing["status"]] = by_status.get(filing["status"], 0) + 1
        mismatch_count += len(filing.get("reconciliation_discrepancies") or [])
    clients = await db.ca_clients.count_documents({"tenant_id": user_tenant_id(ca), "ca_id": ca.user_id, "status": "ACCEPTED"})
    return {
        "clients": clients,
        "total_filings": len(filings),
        "by_status": by_status,
        "open_mismatches": mismatch_count,
        "awaiting_review": by_status.get("under_review", 0),
        "completed": by_status.get("locked", 0),
    }


@api.post("/validation/override-field")
async def override_field(payload: OverrideRequest, reviewer: User = Depends(require_reviewer)):
    filing = await load_filing_or_404(payload.state_id)
    assert_filing_access(reviewer, filing, write=True, review=True)
    # Overrides create evidence and candidate facts. They never mutate canonical facts directly.
    mapping = {
        "gross_salary": "SALARY.GROSS.AGGREGATE",
        "section_10_exemptions": "SALARY.SECTION_10_EXEMPTIONS.AGGREGATE",
        "deductions_80c": "DEDUCTION.80C.CLAIMED",
        "deductions_80d": "DEDUCTION.80D.CLAIMED",
        "other_income": "OTHER_SOURCE.AGGREGATE",
        "house_property_income": "HOUSE_PROPERTY.NET_INCOME.AGGREGATE",
        "stcg_equity": "CAPITAL_GAIN.111A.AGGREGATE",
        "ltcg_equity": "CAPITAL_GAIN.112A.AGGREGATE",
        "tds_deducted": "TAX_CREDIT.TDS.SALARY.AGGREGATE",
    }
    field_code = mapping.get(payload.target_field)
    if not field_code:
        raise HTTPException(status_code=400, detail="Unsupported override field")
    evidence_claim_id = str(uuid.uuid4())
    await db.evidence_claims.insert_one({
        "evidence_claim_id": evidence_claim_id,
        "tenant_id": filing["tenant_id"],
        "case_id": filing["id"],
        "document_id": "MANUAL_CA_DECLARATION",
        "field_code": field_code,
        "original_text": payload.justification,
        "extraction_method": "CA_MANUAL_OVERRIDE_PROPOSAL",
        "parser_version": "manual-v1",
        "raw_value": payload.new_value,
        "created_at": now_iso(),
    })
    candidate = {
        "candidate_fact_id": str(uuid.uuid4()),
        "tenant_id": filing["tenant_id"],
        "case_id": filing["id"],
        "field_code": field_code,
        "value_type": "money",
        "value": {"amount": str(payload.new_value), "currency": "INR"},
        "tax_period": "FY_2025_26",
        "evidence_claim_ids": [evidence_claim_id],
        "idempotency_key": sha256_json({"case": filing["id"], "field": field_code, "value": payload.new_value, "reason": payload.justification}),
        "status": "PENDING_REVIEW",
        "created_by": reviewer.user_id,
        "created_at": now_iso(),
        "reviewed_by": None,
        "reviewed_at": None,
        "review_justification": None,
    }
    await db.candidate_facts.insert_one(candidate.copy())
    return {"status": "PENDING_REVIEW", "candidate_fact": candidate, "message": "Override proposal created. A reviewer must accept it before recomputation."}


@api.get("/filings/{fid}/audit-logs")
async def audit_logs(fid: str, user: User = Depends(get_current_user)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(user, filing)
    modern = await db.audit_events.find({"tenant_id": filing["tenant_id"], "case_id": fid}, {"_id": 0}).sort("occurred_at", -1).to_list(1000)
    legacy = await db.audit_logs.find({"state_id": fid}, {"_id": 0}).sort("timestamp", -1).to_list(1000)
    return {"events": modern, "legacy_events": legacy}


@api.get("/ca/audit-logs")
async def all_audit_logs(ca: User = Depends(require_ca)):
    return await db.audit_events.find({"tenant_id": user_tenant_id(ca)}, {"_id": 0}).sort("occurred_at", -1).to_list(2000)


@api.post("/filings/{fid}/assistant/tools")
async def assistant_tool(fid: str, call: AssistantToolCall, user: User = Depends(get_current_user)):
    filing = await load_filing_or_404(fid)
    assert_filing_access(user, filing, write=call.tool_name in {
        "propose_fact", "create_document_request_draft", "create_client_question_draft"
    })
    context = ToolExecutionContext(
        tenant_id=filing["tenant_id"],
        user_id=user.user_id,
        active_case_id=fid,
        role=user.role,
        permissions=permissions_for_role(user.role),
        request_id=str(uuid.uuid4()),
    )
    gateway = AssistantToolGateway(db)
    return await gateway.execute(context, call, filing)


@api.get("/tax-law/search")
async def tax_law_search(query: str, user: User = Depends(get_current_user)):
    return {"results": search_tax_law(query, "AY 2026-27", "ITA_1961")}


@api.get("/whatsapp/queue")
async def whatsapp_queue(ca: User = Depends(require_ca)):
    return await db.whatsapp_intake.find({"tenant_id": user_tenant_id(ca)}, {"_id": 0}).sort("created_at", -1).to_list(200)


@app.post("/api/v1/integrations/whatsapp")
async def whatsapp_webhook(request: Request, x_webhook_secret: Optional[str] = Header(None)):
    expected = os.environ.get("WHATSAPP_WEBHOOK_SECRET")
    if expected and not secrets.compare_digest(x_webhook_secret or "", expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    if ENVIRONMENT == "production" and not expected:
        raise HTTPException(status_code=503, detail="Webhook is not configured")
    form = await request.form()
    sender = (form.get("From") or "").replace("whatsapp:", "").strip()
    num_media = int(form.get("NumMedia") or 0)
    media_url = form.get("MediaUrl0")
    await db.whatsapp_intake.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": "UNASSIGNED",
        "sender_phone_masked": f"***{sender[-4:]}" if sender else None,
        "media_url": media_url if num_media > 0 else None,
        "status": "QUARANTINED_UNASSIGNED",
        "created_at": now_iso(),
    })
    message = "Thank you. Your message has been quarantined for secure client matching and CA review."
    return FastResponse(content=f"<Response><Message>{message}</Message></Response>", media_type="application/xml")


@api.get("/")
async def root():
    return {
        "service": "Green Papaya",
        "version": "2.0.0",
        "status": "ok",
        "official_itr_export": "disabled_pending_schema_mapper",
    }


app.include_router(api)
allowed_origins = [origin.strip() for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Webhook-Secret"],
)


@app.on_event("startup")
async def startup():
    store.init_storage()
    await db.users.create_index("email", unique=True)
    await db.user_sessions.create_index("session_token_hash", unique=True, sparse=True)
    await db.documents.create_index([("tenant_id", 1), ("filing_id", 1), ("sha256", 1)])
    await db.candidate_facts.create_index([("tenant_id", 1), ("case_id", 1), ("idempotency_key", 1)], unique=True, sparse=True)
    await db.canonical_facts.create_index([("tenant_id", 1), ("case_id", 1), ("field_code", 1), ("is_current", 1)])
    await db.computation_runs.create_index([("tenant_id", 1), ("case_id", 1), ("is_current", 1)])
    logger.info("Green Papaya V2 startup complete")


@app.on_event("shutdown")
async def shutdown():
    client.close()
