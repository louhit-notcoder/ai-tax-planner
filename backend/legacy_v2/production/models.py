from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class UserRole(str, Enum):
    TAXPAYER = "taxpayer"
    FIRM_OWNER = "firm_owner"
    CA_PARTNER = "ca_partner"
    CA_MANAGER = "ca_manager"
    PREPARER = "preparer"
    DOCUMENT_OPERATOR = "document_operator"
    AUDITOR = "auditor"
    CLIENT_PORTAL = "client_portal"


CA_ROLES = {
    UserRole.FIRM_OWNER.value,
    UserRole.CA_PARTNER.value,
    UserRole.CA_MANAGER.value,
    UserRole.PREPARER.value,
    UserRole.DOCUMENT_OPERATOR.value,
    UserRole.AUDITOR.value,
}


class CandidateStatus(str, Enum):
    EXTRACTED = "EXTRACTED"
    VALIDATED = "VALIDATED"
    PENDING_REVIEW = "PENDING_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CONFLICTING = "CONFLICTING"
    SUPERSEDED = "SUPERSEDED"


class ComputationStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PROVISIONAL = "PROVISIONAL"
    BLOCKED = "BLOCKED"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"


class ReviewDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


class MoneyValue(StrictModel):
    amount: Decimal
    currency: Literal["INR", "USD", "GBP", "EUR", "AED", "SGD"] = "INR"

    @field_validator("amount")
    @classmethod
    def finite_amount(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("amount must be finite")
        return value


class EvidenceReference(StrictModel):
    evidence_claim_id: str
    document_id: str
    page_index: int | None = None
    bounding_box: list[float] | None = None
    original_text: str | None = None
    crop_storage_path: str | None = None
    extraction_method: str
    parser_version: str
    model_id: str | None = None


class CandidateFactCreate(StrictModel):
    field_code: str = Field(min_length=3, max_length=120, pattern=r"^[A-Z0-9_.]+$")
    value_type: Literal["money", "date", "text", "boolean", "percentage", "integer"]
    value: dict[str, Any] | str | bool | Decimal | int
    tax_period: str = Field(min_length=4, max_length=20)
    evidence_claim_ids: list[str] = Field(min_length=1, max_length=20)
    extraction_run_id: str | None = None
    model_explanation: str | None = Field(default=None, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=100)


class CandidateFactReview(StrictModel):
    decision: ReviewDecision
    justification: str = Field(min_length=8, max_length=2000)


class ClientQuestionDraftCreate(StrictModel):
    topic: str = Field(min_length=2, max_length=100)
    question: str = Field(min_length=5, max_length=1000)
    context: str = Field(min_length=5, max_length=2000)
    priority: Literal["HIGH", "MEDIUM", "LOW"]


class DocumentRequestDraftCreate(StrictModel):
    document_type: str = Field(min_length=2, max_length=100)
    purpose: str = Field(min_length=5, max_length=1000)
    deadline: date | None = None


class ToolExecutionContext(StrictModel):
    tenant_id: str
    user_id: str
    active_case_id: str
    role: str
    permissions: frozenset[str]
    request_id: str


class AssistantToolCall(StrictModel):
    tool_name: Literal[
        "search_tax_law",
        "read_case_facts",
        "list_missing_information",
        "propose_fact",
        "explain_computation",
        "create_document_request_draft",
        "create_client_question_draft",
        "show_portal_guide",
        "compare_regimes",
        "summarise_discrepancies",
    ]
    arguments: dict[str, Any] = Field(default_factory=dict)


class AssistantFinding(StrictModel):
    title: str
    detail: str
    status: Literal["verified", "provisional", "blocked", "informational"]
    evidence_claim_ids: list[str] = Field(default_factory=list)


class LegalCitation(StrictModel):
    source_id: str
    title: str
    source_type: str
    act_namespace: Literal["ITA_1961", "ITA_2025"]
    section_or_rule: str | None = None
    tax_period: str
    official_url: str


class AssistantResponse(StrictModel):
    response_type: Literal[
        "case_summary",
        "fact_explanation",
        "computation_explanation",
        "missing_information",
        "portal_guide",
        "general_tax_answer",
    ]
    status: Literal["verified", "provisional", "blocked", "informational"]
    summary: str
    findings: list[AssistantFinding] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    tax_impact: str | None = None
    missing_information: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unused_information: list[str] = Field(default_factory=list)
    required_actions: list[dict[str, Any]] = Field(default_factory=list)
    legal_citations: list[LegalCitation] = Field(default_factory=list)
    ca_review_required: bool
    ca_review_reason: str | None = None
    candidate_fact_ids_created: list[str] = Field(default_factory=list)


class AuditEvent(StrictModel):
    event_id: str
    tenant_id: str
    case_id: str | None
    actor_id: str
    actor_role: str
    action: str
    entity_type: str
    entity_id: str | None
    before_hash: str | None = None
    after_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime
