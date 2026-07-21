import os
import json
import uuid
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, Cookie, Response, UploadFile, File, Form, Request
from fastapi.responses import Response as FastResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
import requests

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from tax_engine import engine, TaxComputeRequest, CapitalGainsInput
from crypto_vault import vault
import storage as store
import parser as docparser
from parser import parse_document, parse_documents
import ais_decryptor
from pdf_report import build_computation_pdf

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("green-papaya")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="Green Papaya")
api = APIRouter(prefix="/api")

EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


# ----------------------------- Models -----------------------------
class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    role: str = "taxpayer"          # taxpayer | ca_partner
    pan_hash: Optional[str] = None
    created_at: str

class RoleUpdate(BaseModel):
    role: str

class PanUpdate(BaseModel):
    pan: str
    dob: Optional[str] = None

class LinkClient(BaseModel):
    client_email: str

class FilingCreate(BaseModel):
    assessment_year: str = "AY 2026-27"

class FilingUpdate(BaseModel):
    selected_regime: Optional[str] = None
    selected_itr_form: Optional[str] = None
    parsed_payload: Optional[dict] = None

class OverrideRequest(BaseModel):
    state_id: str
    target_field: str
    new_value: float
    justification: str


# ----------------------------- Auth helpers -----------------------------
async def get_current_user(session_token: Optional[str] = Cookie(None),
                           authorization: Optional[str] = Header(None)) -> User:
    token = session_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
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
    return User(**user)


async def require_ca(user: User = Depends(get_current_user)) -> User:
    if user.role != "ca_partner":
        raise HTTPException(status_code=403, detail="CA access required")
    return user


# ----------------------------- Auth routes -----------------------------
class SessionRequest(BaseModel):
    session_id: str

@api.post("/auth/session")
async def process_session(payload: SessionRequest, response: Response):
    r = requests.get(EMERGENT_SESSION_URL, headers={"X-Session-ID": payload.session_id}, timeout=15)
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session id")
    data = r.json()
    email = data["email"]

    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one({"user_id": user_id},
                                  {"$set": {"name": data.get("name"), "picture": data.get("picture")}})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": data.get("name", email.split("@")[0]),
            "picture": data.get("picture"),
            "role": "unset",
            "pan_hash": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    session_token = data.get("session_token") or uuid.uuid4().hex
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    response.set_cookie("session_token", session_token, httponly=True, secure=True,
                        samesite="none", path="/", max_age=7 * 24 * 60 * 60)
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {"user": User(**user), "session_token": session_token}


@api.get("/auth/me", response_model=User)
async def me(user: User = Depends(get_current_user)):
    return user

@api.post("/auth/logout")
async def logout(response: Response, session_token: Optional[str] = Cookie(None)):
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}

@api.post("/auth/role", response_model=User)
async def set_role(payload: RoleUpdate, user: User = Depends(get_current_user)):
    if payload.role not in ("taxpayer", "ca_partner"):
        raise HTTPException(status_code=400, detail="Invalid role")
    await db.users.update_one({"user_id": user.user_id}, {"$set": {"role": payload.role}})
    doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    return User(**doc)

@api.post("/auth/pan", response_model=User)
async def set_pan(payload: PanUpdate, user: User = Depends(get_current_user)):
    pan_hash = vault.blind_hash(payload.pan)
    await db.secure_metadata.update_one(
        {"user_id": user.user_id},
        {"$set": {"user_id": user.user_id,
                  "pan_encrypted": vault.encrypt(payload.pan),
                  "pan_hash": pan_hash,
                  "dob_encrypted": vault.encrypt(payload.dob) if payload.dob else None}},
        upsert=True,
    )
    await db.users.update_one({"user_id": user.user_id}, {"$set": {"pan_hash": pan_hash}})
    doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    return User(**doc)


# ----------------------------- Tax compute -----------------------------
@api.post("/tax/compute")
async def compute_tax(req: TaxComputeRequest):
    return engine.compute(req).model_dump()


# ----------------------------- Documents -----------------------------
def _mask_pan(pan: Optional[str]):
    if not pan or len(pan) < 4:
        return None
    return pan[:2] + "XXXXX" + pan[-2:]

@api.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), document_type: str = Form("form_16"),
                          filing_id: Optional[str] = Form(None), user: User = Depends(get_current_user)):
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "bin"
    data = await file.read()
    path = f"{store.APP_NAME}/uploads/{user.user_id}/{uuid.uuid4().hex}.{ext}"
    content_type = file.content_type or store.MIME_TYPES.get(ext, "application/octet-stream")
    result = store.put_object(path, data, content_type)
    doc_id = str(uuid.uuid4())
    doc = {
        "id": doc_id,
        "user_id": user.user_id,
        "document_type": document_type,
        "storage_path": result["path"],
        "file_name": file.filename,
        "content_type": content_type,
        "ext": ext,
        "size": result.get("size", len(data)),
        "confidence_score": 0.0,
        "parsed_json": None,
        "filing_id": filing_id,
        "is_purged": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.documents.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api.get("/documents")
async def list_documents(user_id: Optional[str] = None, user: User = Depends(get_current_user)):
    target = user.user_id
    if user_id and user.role == "ca_partner":
        target = user_id
    docs = await db.documents.find({"user_id": target, "is_purged": False}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return docs

@api.get("/documents/{doc_id}")
async def get_document(doc_id: str, user: User = Depends(get_current_user)):
    doc = await db.documents.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc

@api.get("/documents/{doc_id}/download")
async def download_document(doc_id: str, user: User = Depends(get_current_user)):
    doc = await db.documents.find_one({"id": doc_id, "is_purged": False}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc["user_id"] != user.user_id and user.role != "ca_partner":
        raise HTTPException(status_code=403, detail="Access denied")
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()), "state_id": doc.get("filing_id"), "operator_id": user.user_id,
        "modified_field": "DOWNLOAD", "previous_value": None, "new_value": doc["file_name"],
        "justification": "Original document downloaded for review.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    content, ctype = store.get_object(doc["storage_path"])
    return FastResponse(content=content, media_type=doc.get("content_type", ctype),
                        headers={"Content-Disposition": f'inline; filename="{doc["file_name"]}"'})

@api.post("/documents/{doc_id}/parse")
async def parse_doc(doc_id: str, user: User = Depends(get_current_user)):
    doc = await db.documents.find_one({"id": doc_id, "is_purged": False}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    content, _ = store.get_object(doc["storage_path"])
    parsed = await parse_document(content, doc.get("content_type"), doc.get("ext", "pdf"))
    parsed["employee_pan_masked"] = _mask_pan(parsed.get("employee_pan"))
    confidence = parsed.get("confidence", 0.0)
    await db.documents.update_one({"id": doc_id},
                                  {"$set": {"parsed_json": parsed, "confidence_score": confidence}})
    # merge into filing parsed payload
    if doc.get("filing_id"):
        await _merge_parsed_into_filing(doc["filing_id"], parsed)
    return {"parsed_json": parsed, "confidence_score": confidence}


async def _merge_parsed_into_filing(filing_id: str, parsed: dict):
    filing = await db.filings.find_one({"id": filing_id}, {"_id": 0})
    if not filing:
        return
    payload = filing.get("parsed_payload") or {}
    for k in ["gross_salary", "section_10_exemptions", "deductions_80c", "deductions_80d",
              "tds_deducted", "stcg_equity", "ltcg_equity"]:
        val = parsed.get(k, 0) or 0
        if val:
            payload[k] = payload.get(k, 0) + val if k in ("stcg_equity", "ltcg_equity") else val
    if parsed.get("stcg_equity") or parsed.get("ltcg_equity"):
        payload["has_capital_gains"] = True
    await db.filings.update_one({"id": filing_id},
                                {"$set": {"parsed_payload": payload, "status": "under_review",
                                          "updated_at": datetime.now(timezone.utc).isoformat()}})


# ----------------------------- Document rendering & locate (CA desk) -----------------------------
@api.get("/documents/{doc_id}/info")
async def document_info(doc_id: str, user: User = Depends(get_current_user)):
    doc = await db.documents.find_one({"id": doc_id, "is_purged": False}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not docparser.is_pdf_bytes(doc.get("content_type"), doc.get("ext")):
        return {"is_pdf": False, "content_type": doc.get("content_type")}
    content, _ = store.get_object(doc["storage_path"])
    info = docparser.pdf_info(content)
    info["is_pdf"] = True
    return info

@api.get("/documents/{doc_id}/page/{page_index}")
async def document_page(doc_id: str, page_index: int, user: User = Depends(get_current_user)):
    doc = await db.documents.find_one({"id": doc_id, "is_purged": False}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    content, _ = store.get_object(doc["storage_path"])
    png = docparser.render_page_png(content, page_index)
    return FastResponse(content=png, media_type="image/png")

class LocateReq(BaseModel):
    term: str

@api.post("/documents/{doc_id}/locate")
async def document_locate(doc_id: str, payload: LocateReq, user: User = Depends(get_current_user)):
    doc = await db.documents.find_one({"id": doc_id, "is_purged": False}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not docparser.is_pdf_bytes(doc.get("content_type"), doc.get("ext")):
        return {"page": 0, "rects": [], "matched": None}
    content, _ = store.get_object(doc["storage_path"])
    return docparser.locate_term(content, payload.term)


# ----------------------------- Filings -----------------------------
def _compute_for_filing(payload: dict):
    req = TaxComputeRequest(
        gross_salary=payload.get("gross_salary", 0),
        section_10_exemptions=payload.get("section_10_exemptions", 0),
        deductions_80c=payload.get("deductions_80c", 0),
        deductions_80d=payload.get("deductions_80d", 0),
        other_deductions=payload.get("other_deductions", 0),
        other_income=payload.get("other_income", 0),
        house_property_income=payload.get("house_property_income", 0),
        capital_gains=CapitalGainsInput(
            stcg_equity=payload.get("stcg_equity", 0),
            ltcg_equity=payload.get("ltcg_equity", 0),
        ),
    )
    return engine.compute(req).model_dump()

def _suggest_itr(payload: dict) -> str:
    if payload.get("stcg_equity") or payload.get("ltcg_equity") or payload.get("has_capital_gains"):
        return "ITR-2"
    if payload.get("house_property_income"):
        return "ITR-2"
    return "ITR-1"

@api.post("/filings")
async def create_filing(payload: FilingCreate, user: User = Depends(get_current_user)):
    fid = str(uuid.uuid4())
    doc = {
        "id": fid, "user_id": user.user_id, "user_name": user.name, "user_email": user.email,
        "assessment_year": payload.assessment_year, "selected_regime": "NEW",
        "selected_itr_form": "ITR-1", "parsed_payload": {}, "tax_computation_summary": None,
        "reconciliation_discrepancies": [], "status": "not_started", "assigned_ca_id": None,
        "locked": False, "itd_json": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.filings.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api.get("/filings")
async def list_filings(user: User = Depends(get_current_user)):
    if user.role == "ca_partner":
        q = {"assigned_ca_id": user.user_id}
    else:
        q = {"user_id": user.user_id}
    return await db.filings.find(q, {"_id": 0}).sort("updated_at", -1).to_list(500)

@api.get("/filings/{fid}")
async def get_filing(fid: str, user: User = Depends(get_current_user)):
    f = await db.filings.find_one({"id": fid}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Filing not found")
    if f["user_id"] != user.user_id and f.get("assigned_ca_id") != user.user_id and user.role != "ca_partner":
        raise HTTPException(status_code=403, detail="Access denied")
    return f

@api.put("/filings/{fid}")
async def update_filing(fid: str, payload: FilingUpdate, user: User = Depends(get_current_user)):
    f = await db.filings.find_one({"id": fid}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Filing not found")
    if f.get("locked"):
        raise HTTPException(status_code=400, detail="Filing is locked")
    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if payload.selected_regime:
        update["selected_regime"] = payload.selected_regime
    if payload.selected_itr_form:
        update["selected_itr_form"] = payload.selected_itr_form
    merged = f.get("parsed_payload") or {}
    if payload.parsed_payload is not None:
        merged.update(payload.parsed_payload)
        update["parsed_payload"] = merged
    comp = _compute_for_filing(merged)
    update["tax_computation_summary"] = comp
    update["selected_itr_form"] = update.get("selected_itr_form", _suggest_itr(merged))
    await db.filings.update_one({"id": fid}, {"$set": update})
    return await db.filings.find_one({"id": fid}, {"_id": 0})

@api.post("/filings/{fid}/compute")
async def recompute(fid: str, user: User = Depends(get_current_user)):
    f = await db.filings.find_one({"id": fid}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Filing not found")
    comp = _compute_for_filing(f.get("parsed_payload") or {})
    await db.filings.update_one({"id": fid}, {"$set": {"tax_computation_summary": comp,
                                "updated_at": datetime.now(timezone.utc).isoformat()}})
    return comp

@api.post("/filings/{fid}/request-verification")
async def request_verification(fid: str, user: User = Depends(get_current_user)):
    f = await db.filings.find_one({"id": fid}, {"_id": 0})
    if not f or f["user_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="Filing not found")
    link = await db.ca_clients.find_one({"client_id": user.user_id}, {"_id": 0})
    ca_id = link["ca_id"] if link else None
    await db.filings.update_one({"id": fid}, {"$set": {"status": "under_review", "assigned_ca_id": ca_id,
                                "updated_at": datetime.now(timezone.utc).isoformat()}})
    return await db.filings.find_one({"id": fid}, {"_id": 0})

@api.post("/filings/{fid}/reconcile")
async def reconcile(fid: str, user: User = Depends(get_current_user)):
    f = await db.filings.find_one({"id": fid}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Filing not found")
    ais = f.get("ais_prefill")
    if not ais:
        raise HTTPException(status_code=400,
                            detail="No AIS data available. Upload the taxpayer's AIS JSON (from the ITD portal) before reconciling.")
    payload = f.get("parsed_payload") or {}
    flags = _run_reconciliation(payload, ais)
    status = "reconciled" if not flags else "under_review"
    await db.filings.update_one({"id": fid}, {"$set": {
        "reconciliation_discrepancies": flags, "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"discrepancies": flags, "ais_prefill": ais, "status": status}


def _run_reconciliation(payload: dict, ais: dict):
    flags = []
    declared_salary = payload.get("gross_salary", 0)
    ais_salary = ais.get("gross_salary", 0)
    if ais_salary and abs(declared_salary - ais_salary) > 100:
        flags.append({"field": "gross_salary", "severity": "HIGH",
                      "declared": declared_salary, "ais": ais_salary,
                      "message": f"Salary variance: form shows ₹{declared_salary:,.0f}, AIS reports ₹{ais_salary:,.0f}."})
    ais_tds = ais.get("tds_deducted", 0)
    declared_tds = payload.get("tds_deducted", 0)
    if ais_tds and abs(declared_tds - ais_tds) > 100:
        flags.append({"field": "tds_deducted", "severity": "MEDIUM",
                      "declared": declared_tds, "ais": ais_tds,
                      "message": f"TDS variance: form shows ₹{declared_tds:,.0f}, AIS reports ₹{ais_tds:,.0f}."})
    ais_other = ais.get("other_income", 0)
    declared_other = payload.get("other_income", 0)
    if ais_other and abs(ais_other - declared_other) > 100:
        unreported = ais_other - declared_other
        msg = (f"Unreported income: AIS indicates ₹{ais_other:,.0f} dividend/interest, "
               f"₹{unreported:,.0f} more than declared." if unreported > 0
               else f"Declared other income ₹{declared_other:,.0f} exceeds AIS ₹{ais_other:,.0f}.")
        flags.append({"field": "other_income", "severity": "MEDIUM",
                      "declared": declared_other, "ais": ais_other, "message": msg})
    for cg in ("stcg_equity", "ltcg_equity"):
        if ais.get(cg, 0) and abs(payload.get(cg, 0) - ais.get(cg, 0)) > 100:
            flags.append({"field": cg, "severity": "MEDIUM",
                          "declared": payload.get(cg, 0), "ais": ais.get(cg),
                          "message": f"Capital gains variance ({cg}): form ₹{payload.get(cg,0):,.0f} vs AIS ₹{ais.get(cg):,.0f}."})
    if payload.get("deductions_80c", 0) > 150000:
        flags.append({"field": "deductions_80c", "severity": "LOW",
                      "declared": payload.get("deductions_80c"), "ais": 150000,
                      "message": "Section 80C exceeds statutory cap of ₹1,50,000; auto-limited in computation."})
    return flags


@api.post("/filings/{fid}/upload-ais")
async def upload_ais(fid: str, file: UploadFile = File(...), pan: str = Form(""),
                     dob: str = Form(""), password: str = Form(""),
                     user: User = Depends(get_current_user)):
    f = await db.filings.find_one({"id": fid}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Filing not found")
    raw = (await file.read()).decode("utf-8", errors="ignore").strip()
    ais_json = None
    # Accept already-decrypted plain AIS/TIS JSON, else decrypt the ITD utility export.
    if raw.startswith("{") or (raw.startswith("[") and not raw[1:2].isalnum()):
        try:
            ais_json = json.loads(raw)
        except Exception:
            ais_json = None
    if ais_json is None:
        try:
            ais_json = ais_decryptor.decrypt_ais_text(raw, pan, dob, password or None)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"AIS decryption failed: {e}")
    prefill = ais_decryptor.extract_ais_prefill(ais_json)
    payload = f.get("parsed_payload") or {}
    flags = _run_reconciliation(payload, prefill)
    status = "reconciled" if not flags else "under_review"
    await db.filings.update_one({"id": fid}, {"$set": {
        "ais_prefill": prefill, "reconciliation_discrepancies": flags, "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"ais_prefill": prefill, "discrepancies": flags, "status": status,
            "amounts_found": prefill.get("_pairs_found", 0)}


@api.post("/filings/{fid}/parse-documents")
async def parse_documents_endpoint(fid: str, user: User = Depends(get_current_user)):
    """Consolidated multi-file parse: reads all documents attached to the filing."""
    f = await db.filings.find_one({"id": fid}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Filing not found")
    docs = await db.documents.find({"filing_id": fid, "is_purged": False}, {"_id": 0}).to_list(50)
    if not docs:
        raise HTTPException(status_code=400, detail="No documents attached to this filing.")
    files = []
    for d in docs:
        content, _ = store.get_object(d["storage_path"])
        files.append({"bytes": content, "content_type": d.get("content_type"), "ext": d.get("ext", "pdf")})
    parsed = await parse_documents(files)
    parsed["employee_pan_masked"] = _mask_pan(parsed.get("employee_pan"))
    confidence = parsed.get("confidence", 0.0)
    for d in docs:
        await db.documents.update_one({"id": d["id"]},
                                      {"$set": {"parsed_json": parsed, "confidence_score": confidence}})
    await _merge_parsed_into_filing(fid, parsed)
    return {"parsed_json": parsed, "confidence_score": confidence, "documents_analyzed": len(docs)}

@api.post("/filings/{fid}/lock")
async def lock_filing(fid: str, user: User = Depends(require_ca)):
    f = await db.filings.find_one({"id": fid}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Filing not found")
    itd = _build_itd_json(f)
    await db.filings.update_one({"id": fid}, {"$set": {"locked": True, "status": "json_generated",
                                "itd_json": itd, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return await db.filings.find_one({"id": fid}, {"_id": 0})


def _build_itd_json(f: dict) -> dict:
    payload = f.get("parsed_payload") or {}
    comp = f.get("tax_computation_summary") or _compute_for_filing(payload)
    regime = f.get("selected_regime", "NEW")
    tax = comp["tax_liability_new"] if regime == "NEW" else comp["tax_liability_old"]
    return {
        "ITR": {
            "ITR1_ITR2": {
                "CreationInfo": {"SWVersionNo": "1.0", "SWCreatedBy": "GreenPapaya",
                                 "JSONCreatedBy": "GreenPapaya", "JSONCreationDate": datetime.now(timezone.utc).date().isoformat(),
                                 "IntermediaryCity": "Bengaluru", "Digest": uuid.uuid4().hex},
                "Form_ITR": {"FormName": f.get("selected_itr_form", "ITR-1"),
                             "AssessmentYear": f.get("assessment_year", "AY 2026-27").replace("AY ", "").replace("-", ""),
                             "SchemaVer": "Ver1.0", "FormVer": "Ver1.0"},
                "PersonalInfo": {"AssesseeName": {"FirstName": f.get("user_name")},
                                 "PAN": "XXXXX0000X"},
                "ITR1_IncomeDeductions": {
                    "GrossSalary": round(payload.get("gross_salary", 0)),
                    "Salary": round(payload.get("gross_salary", 0)),
                    "AllwncExemptUs10": round(payload.get("section_10_exemptions", 0)),
                    "StandardDeduction": 75000 if regime == "NEW" else 50000,
                    "IncomeFromSal": round(comp["taxable_income_new"] if regime == "NEW" else comp["taxable_income_old"]),
                    "TotalIncomeOfHP": round(payload.get("house_property_income", 0)),
                    "IncomeOthSrc": round(payload.get("other_income", 0)),
                    "GrossTotIncome": round(payload.get("gross_salary", 0) + payload.get("other_income", 0)),
                    "UsrDeductUndChapVIA": {"Section80C": round(min(payload.get("deductions_80c", 0), 150000)),
                                            "Section80D": round(payload.get("deductions_80d", 0))},
                },
                "TaxComputation": {"Regime": regime, "TotalTaxPayable": round(tax),
                                   "CapitalGainsTax": round(comp["stcg_tax"] + comp["ltcg_tax"]),
                                   "EducationCess": round(comp["cess_new"] if regime == "NEW" else comp["cess_old"]),
                                   "RecommendedRegime": comp["recommended_regime"]},
                "TaxPaid": {"TDS": round(payload.get("tds_deducted", 0))},
            }
        }
    }


@api.get("/filings/{fid}/export-json")
async def export_json(fid: str, user: User = Depends(get_current_user)):
    f = await db.filings.find_one({"id": fid}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Filing not found")
    return f.get("itd_json") or _build_itd_json(f)


@api.get("/filings/{fid}/computation-pdf")
async def computation_pdf(fid: str, user: User = Depends(get_current_user)):
    f = await db.filings.find_one({"id": fid}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Filing not found")
    if not f.get("tax_computation_summary"):
        f["tax_computation_summary"] = _compute_for_filing(f.get("parsed_payload") or {})
    pdf_bytes = build_computation_pdf(f)
    fname = f"GreenPapaya_Computation_{f.get('selected_itr_form','ITR')}_{fid[:6]}.pdf"
    return FastResponse(content=pdf_bytes, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ----------------------------- CA console -----------------------------
@api.post("/ca/link-client")
async def link_client(payload: LinkClient, ca: User = Depends(require_ca)):
    clientu = await db.users.find_one({"email": payload.client_email}, {"_id": 0})
    if not clientu:
        raise HTTPException(status_code=404, detail="No taxpayer found with that email")
    await db.ca_clients.update_one(
        {"ca_id": ca.user_id, "client_id": clientu["user_id"]},
        {"$set": {"ca_id": ca.user_id, "client_id": clientu["user_id"],
                  "linked_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    # auto-assign their filings
    await db.filings.update_many({"user_id": clientu["user_id"], "assigned_ca_id": None},
                                 {"$set": {"assigned_ca_id": ca.user_id}})
    return {"linked": clientu["email"], "client_id": clientu["user_id"]}

@api.get("/ca/clients")
async def ca_clients(ca: User = Depends(require_ca)):
    links = await db.ca_clients.find({"ca_id": ca.user_id}, {"_id": 0}).to_list(500)
    out = []
    for l in links:
        u = await db.users.find_one({"user_id": l["client_id"]}, {"_id": 0})
        filings = await db.filings.find({"user_id": l["client_id"]}, {"_id": 0}).to_list(50)
        out.append({"client": {"user_id": u["user_id"], "name": u["name"], "email": u["email"]} if u else None,
                    "filings": filings})
    return out

@api.get("/ca/triage")
async def ca_triage(ca: User = Depends(require_ca)):
    filings = await db.filings.find({"assigned_ca_id": ca.user_id}, {"_id": 0}).sort("updated_at", -1).to_list(500)
    return filings

@api.get("/ca/stats")
async def ca_stats(ca: User = Depends(require_ca)):
    filings = await db.filings.find({"assigned_ca_id": ca.user_id}, {"_id": 0}).to_list(1000)
    clients = await db.ca_clients.count_documents({"ca_id": ca.user_id})
    by_status = {}
    mismatches = 0
    for f in filings:
        by_status[f["status"]] = by_status.get(f["status"], 0) + 1
        mismatches += len(f.get("reconciliation_discrepancies") or [])
    return {"clients": clients, "total_filings": len(filings), "by_status": by_status,
            "open_mismatches": mismatches,
            "awaiting_review": by_status.get("under_review", 0),
            "completed": by_status.get("json_generated", 0) + by_status.get("completed", 0)}

@api.post("/validation/override-field")
async def override_field(payload: OverrideRequest, ca: User = Depends(require_ca)):
    if not payload.justification.strip():
        raise HTTPException(status_code=400, detail="Override justification note is mandatory for compliance logs.")
    f = await db.filings.find_one({"id": payload.state_id}, {"_id": 0})
    if not f:
        raise HTTPException(status_code=404, detail="Filing not found")
    if f.get("locked"):
        raise HTTPException(status_code=400, detail="Filing is locked")
    merged = f.get("parsed_payload") or {}
    previous = merged.get(payload.target_field, 0)
    merged[payload.target_field] = payload.new_value
    comp = _compute_for_filing(merged)
    await db.filings.update_one({"id": payload.state_id},
                                {"$set": {"parsed_payload": merged, "tax_computation_summary": comp,
                                          "updated_at": datetime.now(timezone.utc).isoformat()}})
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()), "state_id": payload.state_id, "operator_id": ca.user_id,
        "operator_name": ca.name, "modified_field": payload.target_field,
        "previous_value": str(previous), "new_value": str(payload.new_value),
        "justification": payload.justification, "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {"status": "success", "updated_tax_new": comp["tax_liability_new"],
            "updated_tax_old": comp["tax_liability_old"], "recommended_regime": comp["recommended_regime"],
            "computation": comp}

@api.get("/filings/{fid}/audit-logs")
async def audit_logs(fid: str, user: User = Depends(get_current_user)):
    logs = await db.audit_logs.find({"state_id": fid}, {"_id": 0}).sort("timestamp", -1).to_list(500)
    return logs

@api.get("/ca/audit-logs")
async def all_audit_logs(ca: User = Depends(require_ca)):
    filings = await db.filings.find({"assigned_ca_id": ca.user_id}, {"_id": 0, "id": 1}).to_list(1000)
    ids = [f["id"] for f in filings]
    logs = await db.audit_logs.find({"state_id": {"$in": ids}}, {"_id": 0}).sort("timestamp", -1).to_list(1000)
    return logs


# ----------------------------- WhatsApp provision -----------------------------
@api.get("/whatsapp/queue")
async def whatsapp_queue(ca: User = Depends(require_ca)):
    items = await db.whatsapp_intake.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items

@app.post("/api/v1/integrations/whatsapp")
async def whatsapp_webhook(request: Request):
    """Twilio WhatsApp webhook provision. Ready to wire real Twilio credentials."""
    form = await request.form()
    sender = (form.get("From") or "").replace("whatsapp:", "").strip()
    num_media = int(form.get("NumMedia") or 0)
    media_url = form.get("MediaUrl0")
    if num_media > 0 and media_url:
        await db.whatsapp_intake.insert_one({
            "id": str(uuid.uuid4()), "sender_phone": sender, "media_url": media_url,
            "status": "received", "created_at": datetime.now(timezone.utc).isoformat()})
        msg = ("Thank you! Green Papaya received your document. Our parsing engine is running "
               "and your CA will review the return.")
    else:
        msg = ("Hello! Welcome to Green Papaya. Please upload your Form 16 PDF or broker "
               "statement here to begin your tax computation.")
    twiml = f"<Response><Message>{msg}</Message></Response>"
    return FastResponse(content=twiml, media_type="application/xml")


@api.get("/")
async def root():
    return {"service": "Green Papaya", "status": "ok"}


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origin_regex=".*",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    try:
        store.init_storage()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")


@app.on_event("shutdown")
async def shutdown():
    client.close()
