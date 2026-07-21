from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from .facts import create_candidate_fact, list_current_canonical_facts
from .legal_sources import PORTAL_GUIDES, search_tax_law
from .missing_info import list_missing_information
from .models import (
    AssistantToolCall,
    CandidateFactCreate,
    ClientQuestionDraftCreate,
    DocumentRequestDraftCreate,
    ToolExecutionContext,
)


CAPABILITIES = {
    "search_tax_law": "tax_law:search",
    "read_case_facts": "case_facts:read",
    "list_missing_information": "case_missing_items:read",
    "propose_fact": "fact_candidate:create",
    "explain_computation": "computation:explain",
    "create_document_request_draft": "document_request_draft:create",
    "create_client_question_draft": "client_question_draft:create",
    "show_portal_guide": "portal_guide:read",
    "compare_regimes": "regime_comparison:read",
    "summarise_discrepancies": "discrepancy_summary:read",
}


class AssistantToolGateway:
    def __init__(self, db):
        self.db = db

    async def execute(self, context: ToolExecutionContext, call: AssistantToolCall, filing: dict) -> dict:
        required = CAPABILITIES[call.tool_name]
        if required not in context.permissions:
            raise HTTPException(status_code=403, detail=f"AI capability denied: {required}")
        if filing["id"] != context.active_case_id:
            raise HTTPException(status_code=403, detail="Tool context is not bound to the active case")

        handler = getattr(self, f"_tool_{call.tool_name}", None)
        if handler is None:
            raise HTTPException(status_code=400, detail="Unregistered tool")
        result = await handler(context, filing, call.arguments)
        await self.db.ai_tool_audit.insert_one({
            "tool_audit_id": str(uuid.uuid4()),
            "tenant_id": context.tenant_id,
            "case_id": context.active_case_id,
            "actor_id": context.user_id,
            "request_id": context.request_id,
            "tool_name": call.tool_name,
            "argument_keys": sorted(call.arguments.keys()),
            "result_summary": {"keys": sorted(result.keys()) if isinstance(result, dict) else []},
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return result

    async def _tool_search_tax_law(self, context, filing, args):
        query = str(args.get("query", "")).strip()
        if not query:
            raise HTTPException(status_code=400, detail="query is required")
        return {"results": search_tax_law(query, filing.get("assessment_year", "AY 2026-27"), "ITA_1961")}

    async def _tool_read_case_facts(self, context, filing, args):
        facts = await list_current_canonical_facts(self.db, tenant_id=context.tenant_id, case_id=context.active_case_id)
        # Return only values needed for tax work; encrypted personal data is never returned here.
        return {"case_id": context.active_case_id, "facts": facts}

    async def _tool_list_missing_information(self, context, filing, args):
        return {"items": await list_missing_information(self.db, tenant_id=context.tenant_id, case_id=context.active_case_id, filing=filing)}

    async def _tool_propose_fact(self, context, filing, args):
        request = CandidateFactCreate.model_validate(args)
        fact = await create_candidate_fact(
            self.db,
            tenant_id=context.tenant_id,
            case_id=context.active_case_id,
            actor_id=context.user_id,
            request=request,
        )
        return {"candidate_fact": fact, "message": "Candidate created for CA review; computation was not changed."}

    async def _tool_explain_computation(self, context, filing, args):
        line_code = str(args.get("calculation_line", "")).strip()
        run = await self.db.computation_runs.find_one({
            "tenant_id": context.tenant_id,
            "case_id": context.active_case_id,
            "is_current": True,
        }, {"_id": 0})
        if not run:
            raise HTTPException(status_code=404, detail="No computation exists for this case")
        line = next((item for item in run["result"].get("calculation_lines", []) if item.get("code") == line_code), None)
        if not line:
            raise HTTPException(status_code=404, detail="Calculation line not found")
        return {"calculation_line": line, "source": "stored_deterministic_trace"}

    async def _tool_create_document_request_draft(self, context, filing, args):
        request = DocumentRequestDraftCreate.model_validate(args)
        doc = {
            "document_request_draft_id": str(uuid.uuid4()),
            "tenant_id": context.tenant_id,
            "case_id": context.active_case_id,
            **request.model_dump(mode="json"),
            "status": "DRAFT",
            "created_by": context.user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.document_request_drafts.insert_one(doc.copy())
        return {"draft": doc, "sent": False}

    async def _tool_create_client_question_draft(self, context, filing, args):
        request = ClientQuestionDraftCreate.model_validate(args)
        doc = {
            "client_question_draft_id": str(uuid.uuid4()),
            "tenant_id": context.tenant_id,
            "case_id": context.active_case_id,
            **request.model_dump(mode="json"),
            "status": "DRAFT",
            "created_by": context.user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.client_question_drafts.insert_one(doc.copy())
        return {"draft": doc, "sent": False}

    async def _tool_show_portal_guide(self, context, filing, args):
        action = str(args.get("action", ""))
        guide = PORTAL_GUIDES.get(action)
        if not guide:
            raise HTTPException(status_code=404, detail="Approved portal guide not found")
        return {"guide": guide, "status": "REVIEW_BEFORE_SENDING"}

    async def _tool_compare_regimes(self, context, filing, args):
        run = await self.db.computation_runs.find_one({
            "tenant_id": context.tenant_id,
            "case_id": context.active_case_id,
            "is_current": True,
        }, {"_id": 0})
        if not run:
            raise HTTPException(status_code=404, detail="No computation exists for this case")
        result = run["result"]
        return {
            "old_regime": result.get("tax_liability_old"),
            "new_regime": result.get("tax_liability_new"),
            "recommended_regime": result.get("recommended_regime"),
            "savings": result.get("savings_with_recommended"),
            "computation_status": result.get("computation_status"),
        }

    async def _tool_summarise_discrepancies(self, context, filing, args):
        items = filing.get("reconciliation_discrepancies") or []
        return {
            "count": len(items),
            "high": sum(1 for item in items if item.get("severity") == "HIGH"),
            "items": items,
            "note": "This is a summary of stored reconciliation items; it does not resolve them.",
        }
