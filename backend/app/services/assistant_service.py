from __future__ import annotations

import os
from datetime import date
from typing import Any

import requests
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import append_audit
from ..db_models import (
    CanonicalFact,
    CandidateFact,
    ClientQuestionDraft,
    ComputationRun,
    Document,
    DocumentRequestDraft,
    EvidenceClaim,
    MissingItem,
    ReconciliationItem,
)
from ..legal.retrieval import search_approved_sources
from ..security import Actor, assert_case_access, has_permission
from .facts_service import propose_candidate

TOOL_PERMISSION = {
    "search_tax_law": "assistant:*",
    "read_case_facts": "assistant:*",
    "list_documents": "assistant:*",
    "read_document_evidence": "assistant:*",
    "list_missing_information": "assistant:*",
    "propose_fact": "fact:propose",
    "explain_computation": "computation:read",
    "create_document_request_draft": "assistant:*",
    "create_client_question_draft": "assistant:*",
    "show_portal_guide": "assistant:*",
    "compare_regimes": "computation:read",
    "summarise_discrepancies": "reconciliation:*",
    "run_reconciliation": "reconciliation:*",
    "summarise_case": "assistant:*",
    "run_computation": "computation:run",
}

PORTAL_GUIDES = {
    "download_ais": [
        "Sign in to the Income Tax e-Filing portal.",
        "Open Services and select Annual Information Statement (AIS).",
        "Select the relevant financial year.",
        "Download AIS in JSON where available; keep the original file unchanged.",
        "Upload the downloaded file to the active Green Papaya case.",
    ],
    "download_26as": [
        "Sign in to the Income Tax e-Filing portal.",
        "Open e-File, Income Tax Returns, then View Form 26AS.",
        "Continue to the authorised TDS portal.",
        "Select the assessment year and download the text/PDF statement.",
        "Upload the original downloaded statement to the active case.",
    ],
    "download_prefill_json": [
        "Sign in to the Income Tax e-Filing portal.",
        "Open e-File, Income Tax Returns, File Income Tax Return.",
        "Select the assessment year and Offline mode.",
        "Download pre-filled data JSON and upload it without editing.",
    ],
}


class AssistantToolGateway:
    def execute(self, db: Session, *, actor: Actor, case_id: str, name: str, arguments: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        case = assert_case_access(db, actor, case_id, "case:read")
        permission = TOOL_PERMISSION.get(name)
        if not permission or not has_permission(actor.role, permission):
            raise HTTPException(status_code=403, detail="AI tool capability denied")
        handler = getattr(self, f"tool_{name}", None)
        if handler is None:
            raise HTTPException(status_code=400, detail="Unregistered AI tool")
        result = handler(db, actor, case, arguments, idempotency_key)
        append_audit(db, actor=actor, action=f"assistant_tool.{name}", entity_type="tax_case", entity_id=case.id, case_id=case.id, after={"result_type": result.get("type")}, metadata={"idempotency_key": idempotency_key})
        return result

    def tool_search_tax_law(self, db, actor, case, args, _key):
        query = str(args.get("query", "")).strip()
        if not query:
            raise HTTPException(status_code=400, detail="query is required")
        passages = search_approved_sources(db, query=query, tax_period=case.assessment_year, act_namespace=case.act_namespace)
        return {"type": "legal_search", "verified": bool(passages), "results": [item.__dict__ for item in passages], "message": None if passages else "No approved official source matched this question. CA legal review is required."}

    def tool_read_case_facts(self, db, actor, case, args, _key):
        rows = list(db.scalars(select(CanonicalFact).where(CanonicalFact.tenant_id == actor.tenant_id, CanonicalFact.case_id == case.id, CanonicalFact.is_current.is_(True))))
        return {"type": "case_facts", "facts": [{"id": row.id, "field_code": row.field_code, "entity_key": row.entity_key, "value": row.value_json, "evidence_claim_ids": row.evidence_claim_ids, "version": row.version} for row in rows]}

    def tool_list_documents(self, db, actor, case, args, _key):
        rows = list(db.scalars(select(Document).where(Document.tenant_id == actor.tenant_id, Document.case_id == case.id).order_by(Document.created_at.desc())))
        return {
            "type": "document_list",
            "documents": [
                {
                    "id": r.id,
                    "filename": r.original_filename,
                    "document_type": r.document_type,
                    "state": r.state,
                    "requires_password": r.state == "PASSWORD_REQUIRED",
                }
                for r in rows
            ],
        }

    def tool_read_document_evidence(self, db, actor, case, args, _key):
        doc_id = args.get("document_id")
        filename = args.get("filename")
        doc = None
        if doc_id:
            doc = db.scalar(select(Document).where(Document.id == doc_id, Document.tenant_id == actor.tenant_id))
        elif filename:
            doc = db.scalar(select(Document).where(Document.original_filename.ilike(f"%{filename}%"), Document.tenant_id == actor.tenant_id, Document.case_id == case.id))
        if not doc:
            docs = list(db.scalars(select(Document).where(Document.tenant_id == actor.tenant_id, Document.case_id == case.id)))
            if docs:
                doc = docs[0]
        if not doc:
            return {"type": "document_evidence", "found": False, "message": "No document found for this case."}

        claims = list(db.scalars(select(EvidenceClaim).where(EvidenceClaim.document_id == doc.id).order_by(EvidenceClaim.page_index)))
        candidates = list(db.scalars(select(CandidateFact).where(CandidateFact.tenant_id == actor.tenant_id, CandidateFact.case_id == case.id)))

        return {
            "type": "document_evidence",
            "found": True,
            "document": {"id": doc.id, "filename": doc.original_filename, "type": doc.document_type, "state": doc.state},
            "evidence_claims": [
                {
                    "field_code": c.field_code,
                    "value_type": c.value_type,
                    "value": c.value_json,
                    "original_text": c.original_text,
                    "page_index": c.page_index,
                }
                for c in claims
            ],
            "extracted_facts": [
                {
                    "id": f.id,
                    "field_code": f.field_code,
                    "value": f.value_json,
                    "status": f.status,
                }
                for f in candidates
            ],
        }

    def tool_list_missing_information(self, db, actor, case, args, _key):
        rows = list(db.scalars(select(MissingItem).where(MissingItem.tenant_id == actor.tenant_id, MissingItem.case_id == case.id, MissingItem.status == "OPEN")))
        return {"type": "missing_information", "items": [{"id": row.id, "code": row.code, "title": row.title, "reason": row.reason, "priority": row.priority, "blocking": row.blocking} for row in rows]}

    def tool_propose_fact(self, db, actor, case, args, key):
        allowed = {"field_code", "entity_key", "value_type", "value", "evidence_claim_ids", "model_explanation"}
        unknown = set(args) - allowed
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown propose_fact fields: {sorted(unknown)}")
        candidate = propose_candidate(db, actor=actor, case_id=case.id, field_code=args["field_code"], entity_key=args.get("entity_key", "ROOT"), value_type=args["value_type"], value=args["value"], evidence_claim_ids=args.get("evidence_claim_ids", []), idempotency_key=f"ai:{key}", source="AI", explanation=args.get("model_explanation"))
        return {"type": "candidate_fact", "candidate_fact_id": candidate.id, "status": candidate.status, "ca_review_required": True}

    def tool_explain_computation(self, db, actor, case, args, _key):
        run = db.scalar(select(ComputationRun).where(ComputationRun.tenant_id == actor.tenant_id, ComputationRun.case_id == case.id).order_by(ComputationRun.created_at.desc()))
        if not run:
            raise HTTPException(status_code=404, detail="No computation exists")
        code = str(args.get("calculation_line", ""))
        line = next((line for line in run.result_json.get("calculation_lines", []) if line.get("code") == code or line.get("line_id") == code), None)
        if not line:
            raise HTTPException(status_code=404, detail="Calculation line not found")
        return {"type": "computation_explanation", "status": "VERIFIED", "line": line, "message": f"{line['label']} was calculated as {line['formula']} and resulted in ₹{line['result']}."}

    def tool_create_document_request_draft(self, db, actor, case, args, key):
        existing = db.scalar(select(DocumentRequestDraft).where(DocumentRequestDraft.tenant_id == actor.tenant_id, DocumentRequestDraft.case_id == case.id, DocumentRequestDraft.created_by == f"AI:{key}"))
        if existing:
            return {"type": "document_request_draft", "draft_id": existing.id, "status": existing.status}
        deadline = date.fromisoformat(args["deadline"]) if args.get("deadline") else None
        draft = DocumentRequestDraft(tenant_id=actor.tenant_id, case_id=case.id, document_type=str(args["document_type"]), purpose=str(args["purpose"]), deadline=deadline, status="DRAFT", created_by=f"AI:{key}")
        db.add(draft); db.flush()
        return {"type": "document_request_draft", "draft_id": draft.id, "status": draft.status, "human_approval_required": True}

    def tool_create_client_question_draft(self, db, actor, case, args, key):
        existing = db.scalar(select(ClientQuestionDraft).where(ClientQuestionDraft.tenant_id == actor.tenant_id, ClientQuestionDraft.case_id == case.id, ClientQuestionDraft.created_by == f"AI:{key}"))
        if existing:
            return {"type": "client_question_draft", "draft_id": existing.id, "status": existing.status}
        priority = str(args.get("priority", "MEDIUM")).upper()
        if priority not in {"HIGH", "MEDIUM", "LOW"}:
            raise HTTPException(status_code=400, detail="Invalid priority")
        draft = ClientQuestionDraft(tenant_id=actor.tenant_id, case_id=case.id, topic=str(args["topic"]), question=str(args["question"]), context=str(args.get("context", "")), priority=priority, status="DRAFT", created_by=f"AI:{key}")
        db.add(draft); db.flush()
        return {"type": "client_question_draft", "draft_id": draft.id, "status": draft.status, "human_approval_required": True}

    def tool_show_portal_guide(self, db, actor, case, args, _key):
        action = str(args.get("action", ""))
        steps = PORTAL_GUIDES.get(action)
        if not steps:
            raise HTTPException(status_code=404, detail="No approved portal guide exists for this action")
        return {"type": "portal_guide", "action": action, "portal": args.get("portal", "income_tax"), "steps": steps, "reviewed_version": "2026-07-21"}

    def tool_compare_regimes(self, db, actor, case, args, _key):
        run = db.scalar(select(ComputationRun).where(ComputationRun.tenant_id == actor.tenant_id, ComputationRun.case_id == case.id).order_by(ComputationRun.created_at.desc()))
        if not run:
            raise HTTPException(status_code=404, detail="No computation exists")
        return {"type": "regime_comparison", "old": run.result_json.get("old_regime"), "new": run.result_json.get("new_regime"), "recommended": run.result_json.get("recommended_regime"), "result_hash": run.result_hash}

    def tool_summarise_discrepancies(self, db, actor, case, args, _key):
        rows = list(db.scalars(select(ReconciliationItem).where(ReconciliationItem.tenant_id == actor.tenant_id, ReconciliationItem.case_id == case.id)))
        return {"type": "discrepancy_summary", "items": [{"id": row.id, "category": row.category, "status": row.status, "source_values": row.source_values, "difference_amount": str(row.difference_amount) if row.difference_amount is not None else None, "resolution_note": row.resolution_note} for row in rows]}

    def tool_run_reconciliation(self, db, actor, case, args, _key):
        from .reconciliation_service import rebuild_reconciliation
        result = rebuild_reconciliation(db, actor, case.id)
        return {"type": "reconciliation", "difference_count": result["difference_count"], "items": result["reconciliation"]}

    def tool_summarise_case(self, db, actor, case, args, _key):
        from .case_summary_service import build_case_summary
        return {"type": "case_summary", **build_case_summary(db, actor, case.id)}

    def tool_run_computation(self, db, actor, case, args, _key):
        from .computation_service import run_computation
        regime = args.get("selected_regime") or case.selected_regime
        run = run_computation(db, actor=actor, case_id=case.id, selected_regime=regime)
        result = run.result_json or {}
        selected = result.get("selected_result") or {}
        return {
            "type": "computation",
            "status": result.get("status"),
            "recommended_regime": result.get("recommended_regime"),
            "selected_regime": result.get("selected_regime"),
            "total_income": selected.get("total_income"),
            "total_tax_liability": selected.get("total_tax_liability"),
            "payable": selected.get("payable"),
            "refund": selected.get("refund"),
            "blocker_count": len(result.get("blockers") or []),
            "warning_count": len(result.get("warnings") or []),
        }


gateway = AssistantToolGateway()


class OpenRouterModelClient:
    """Optional model client. It cannot access the database and only returns tool calls/text.

    Production should allowlist provider/model combinations that passed the evaluation suite.
    """

    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.model = os.getenv("OPENROUTER_ASSISTANT_MODEL", "")
        self.base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        # Zero-data-retention routing is opt-in: many providers (e.g. Google Gemini
        # on OpenRouter) expose no ZDR route, and forcing it makes every request fail.
        # data_collection stays "deny" so the provider still cannot train on the data.
        self.require_zdr = os.getenv("OPENROUTER_REQUIRE_ZDR", "false").lower() == "true"

    def enabled(self) -> bool:
        return bool(self.api_key and self.model)

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.enabled():
            raise RuntimeError("OpenRouter assistant is not configured")
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Title": "Green Papaya Tax Assistant",
            },
            json={
                "model": self.model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0,
                "provider": {"data_collection": "deny", "zdr": self.require_zdr},
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
