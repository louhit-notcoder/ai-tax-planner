"""Conversational tax-assistant orchestration.

This wires the existing server-controlled `AssistantToolGateway` and the
`OpenRouterModelClient` into a real chat loop. The model never touches the
database directly and never performs arithmetic that lands in the return: it can
only call the audited, permission-checked tools in the gateway (search approved
law, read reviewed facts, explain the deterministic computation, draft questions
for CA approval, etc.). All tax numbers still come from the deterministic engine
and remain evidence-linked and maker-checker gated.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import ChatMessage, Client
from ..security import Actor, assert_case_access
from .assistant_service import OpenRouterModelClient, gateway

MAX_TOOL_STEPS = 6
HISTORY_LIMIT = 24

SYSTEM_PROMPT = """You are Green Papaya, an expert assistant for Indian Chartered Accountants preparing income-tax returns for Assessment Year 2026-27 (Financial Year 2025-26).

Your job is to help the CA organise a client's information, understand it, and reach a correct, defensible tax computation. You behave like a careful, senior tax professional with a warm, hand-holding, explanatory style.

CORE RULES — these are absolute:
1. NEVER invent numbers, section references, due dates, or rules. If you are not certain, say so and use the `search_tax_law` tool to check an approved official source, or ask the CA.
2. You do NOT compute the final tax yourself. The deterministic engine does that. You may read and EXPLAIN its output using `explain_computation` and `compare_regimes`, but never state a tax figure you did not read from a tool result.
3. Every material claim about this client's numbers must come from a tool result (`read_case_facts`, `explain_computation`, `compare_regimes`, `summarise_discrepancies`). Do not rely on memory of the conversation for figures.
4. You cannot approve facts, change rules, or file a return. When the client needs to answer something or provide a document, create a draft with `create_client_question_draft` or `create_document_request_draft` — a human CA approves it before it is sent.

HOW TO WORK A CASE:
- When documents have been uploaded, call `read_case_facts` to see what has been extracted and reviewed, and `list_missing_information` to see gaps.
- Summarise the client's situation in plain language: salary/Form 16, house property, capital gains (listed equity, mutual funds, property), business/presumptive/F&O, other income, foreign income/assets (flag if Schedule FA / FSI / FTC / Form 67 may be needed), and deductions.
- Proactively ask about likely-missing items: "Did the client sell any property or shares this year?", "Any foreign bank accounts, RSUs, or ESOPs?", "Interest from savings/FDs?", "Home loan?".
- When the CA asks about a rule or limit, verify with `search_tax_law` rather than answering from memory.
- Explain the recommended regime and the computation in clear, itemised terms the CA can defend.
- When you need the client to fetch something (AIS, 26AS, pre-filled JSON), use `show_portal_guide` to give exact portal steps.

STYLE:
- Be concise but complete. Use short paragraphs and bullet points.
- Show rupee amounts with ₹ and Indian formatting when quoting tool results.
- Always make clear what is confirmed (from evidence) versus what still needs the CA's or client's input.
"""


def _tool_schemas() -> list[dict[str, Any]]:
    def fn(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required or [],
                    "additionalProperties": False,
                },
            },
        }

    return [
        fn("search_tax_law", "Search approved official Indian tax sources for a provision, limit, rate or rule. Use this instead of answering rule questions from memory.",
           {"query": {"type": "string", "description": "The tax question or provision to look up."}}, ["query"]),
        fn("read_case_facts", "Read the current CA-reviewed canonical facts extracted for this client (income, deductions, etc.). Use before summarising the client's situation.", {}),
        fn("list_missing_information", "List open missing-information items and blockers for this case.", {}),
        fn("explain_computation", "Explain a single line of the latest deterministic tax computation. Provide the calculation line code.",
           {"calculation_line": {"type": "string", "description": "The code or line_id of the calculation line to explain."}}, ["calculation_line"]),
        fn("compare_regimes", "Return the old-regime vs new-regime totals and the recommended regime from the latest computation.", {}),
        fn("summarise_discrepancies", "Summarise reconciliation discrepancies across sources (e.g. AIS vs broker vs Form 16).", {}),
        fn("show_portal_guide", "Return the approved step-by-step guide for downloading a document from the income-tax portal.",
           {"action": {"type": "string", "enum": ["download_ais", "download_26as", "download_prefill_json"]},
            "portal": {"type": "string"}}, ["action"]),
        fn("create_document_request_draft", "Draft a request asking the client to provide a document. A CA must approve it before it is sent.",
           {"document_type": {"type": "string"}, "purpose": {"type": "string"}, "deadline": {"type": "string", "description": "Optional ISO date YYYY-MM-DD."}},
           ["document_type", "purpose"]),
        fn("create_client_question_draft", "Draft a clarifying question for the client (e.g. about a property sale or foreign asset). A CA must approve it before it is sent.",
           {"topic": {"type": "string"}, "question": {"type": "string"}, "context": {"type": "string"},
            "priority": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]}}, ["topic", "question"]),
    ]


def _load_history(db: Session, actor: Actor, case_id: str) -> list[ChatMessage]:
    rows = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.tenant_id == actor.tenant_id, ChatMessage.case_id == case_id)
            .order_by(ChatMessage.created_at.asc())
        )
    )
    return rows[-HISTORY_LIMIT:]


def list_messages(db: Session, actor: Actor, case_id: str) -> list[dict[str, Any]]:
    assert_case_access(db, actor, case_id, "assistant:*")
    rows = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.tenant_id == actor.tenant_id, ChatMessage.case_id == case_id)
            .order_by(ChatMessage.created_at.asc())
        )
    )
    return [{"id": r.id, "role": r.role, "content": r.content, "tool_trace": r.tool_trace, "created_at": r.created_at.isoformat()} for r in rows]


def _persist(db: Session, actor: Actor, case_id: str, role: str, content: str, tool_trace: list | None = None) -> ChatMessage:
    row = ChatMessage(tenant_id=actor.tenant_id, case_id=case_id, role=role, content=content, tool_trace=tool_trace or [], created_by=actor.user_id)
    db.add(row)
    db.flush()
    return row


def run_chat(db: Session, actor: Actor, case_id: str, user_message: str) -> dict[str, Any]:
    """Run one conversational turn. Returns the persisted assistant message."""
    case = assert_case_access(db, actor, case_id, "assistant:*")
    history = _load_history(db, actor, case_id)
    _persist(db, actor, case_id, "user", user_message)

    client = OpenRouterModelClient()
    if not client.enabled():
        text = (
            "The AI assistant is not configured yet. Ask your administrator to set "
            "`OPENROUTER_API_KEY` and `OPENROUTER_ASSISTANT_MODEL` on the backend. "
            "Everything else in this workspace — document upload, fact review, the "
            "deterministic computation and export — still works without it."
        )
        row = _persist(db, actor, case_id, "assistant", text)
        db.commit()
        return {"id": row.id, "role": "assistant", "content": text, "tool_trace": []}

    client_row = db.scalar(select(Client).where(Client.id == case.client_id, Client.tenant_id == actor.tenant_id))
    client_name = getattr(client_row, "display_name", None) or "the client"
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.append({"role": "system", "content": f"Active case context: client={client_name!r}, tax_period={case.tax_period}, assessment_year={case.assessment_year}, selected_regime={case.selected_regime}, status={case.status}."})
    for row in history:
        if row.role in {"user", "assistant"} and row.content:
            messages.append({"role": row.role, "content": row.content})
    messages.append({"role": "user", "content": user_message})

    tools = _tool_schemas()
    tool_trace: list[dict[str, Any]] = []

    try:
        for _step in range(MAX_TOOL_STEPS):
            completion = client.complete(messages, tools)
            choice = (completion.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                final_text = (msg.get("content") or "").strip() or "I wasn't able to produce a response. Please rephrase or try again."
                row = _persist(db, actor, case_id, "assistant", final_text, tool_trace)
                db.commit()
                return {"id": row.id, "role": "assistant", "content": final_text, "tool_trace": tool_trace}

            # Record the assistant's tool-call turn, then execute each call.
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls})
            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name", "")
                try:
                    arguments = json.loads(fn.get("arguments") or "{}")
                except (json.JSONDecodeError, TypeError):
                    arguments = {}
                try:
                    result = gateway.execute(db, actor=actor, case_id=case_id, name=name, arguments=arguments, idempotency_key=f"chat:{call.get('id', name)}")
                    tool_trace.append({"tool": name, "ok": True, "type": result.get("type")})
                except Exception as exc:  # surface tool errors back to the model instead of crashing
                    result = {"type": "error", "error": str(getattr(exc, "detail", exc))}
                    tool_trace.append({"tool": name, "ok": False, "type": "error"})
                messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": json.dumps(result, default=str)})

        # Exhausted tool steps without a final answer.
        text = "I gathered the information but need another step. Please ask me to continue or narrow the question."
        row = _persist(db, actor, case_id, "assistant", text, tool_trace)
        db.commit()
        return {"id": row.id, "role": "assistant", "content": text, "tool_trace": tool_trace}
    except Exception as exc:  # network/model failure — never 500 the chat
        text = f"The assistant hit an error talking to the model provider: {exc}. Please try again in a moment."
        row = _persist(db, actor, case_id, "assistant", text, tool_trace)
        db.commit()
        return {"id": row.id, "role": "assistant", "content": text, "tool_trace": tool_trace}
