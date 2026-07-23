from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class BootstrapRequest(StrictModel):
    firm_name: str = Field(min_length=2, max_length=200)
    firm_slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")
    owner_name: str = Field(min_length=2, max_length=200)
    owner_email: EmailStr
    password: str = Field(min_length=12, max_length=200)


class SignupRequest(StrictModel):
    # Self-serve firm signup: no slug to invent (auto-generated), lighter password
    # floor so getting into the product is one short form.
    firm_name: str = Field(min_length=2, max_length=200)
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(StrictModel):
    email: EmailStr
    password: str
    tenant_slug: str | None = None
    totp_code: str | None = Field(default=None, pattern=r"^[0-9]{6}$")


class RefreshRequest(StrictModel):
    refresh_token: str | None = Field(default=None, min_length=32)


class InvitationRequest(StrictModel):
    email: EmailStr
    role: Literal["ca_partner", "ca_manager", "preparer", "document_operator", "auditor", "client_portal"]
    expires_days: int = Field(default=7, ge=1, le=30)


class AcceptInvitationRequest(StrictModel):
    token: str = Field(min_length=32)
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=12, max_length=200)


class MFAConfirmRequest(StrictModel):
    code: str = Field(pattern=r"^[0-9]{6}$")


class ClientCreate(StrictModel):
    display_name: str = Field(min_length=2, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    pan: str | None = Field(default=None, pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$")
    date_of_birth: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseCreate(StrictModel):
    client_id: str
    tax_period: str = "FY 2025-26"
    assessment_year: str = "AY 2026-27"
    selected_regime: Literal["OLD", "NEW"] = "NEW"
    preparer_id: str | None = None
    reviewer_id: str | None = None
    due_date: date | None = None


class CaseAssignmentUpdate(StrictModel):
    preparer_id: str | None = None
    reviewer_id: str | None = None


class CandidateProposal(StrictModel):
    field_code: str = Field(min_length=3, max_length=160)
    entity_key: str = Field(default="ROOT", min_length=1, max_length=160)
    value_type: Literal["money", "date", "text", "boolean", "percentage", "object", "array"]
    value: dict[str, Any]
    evidence_claim_ids: list[str] = Field(default_factory=list)
    model_explanation: str | None = Field(default=None, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=160)


class CandidateReview(StrictModel):
    decision: Literal["ACCEPT", "REJECT", "CONFLICT"]
    justification: str = Field(min_length=8, max_length=3000)
    corrected_value: dict[str, Any] | None = None
    entity_key: str | None = Field(default=None, max_length=160)


class SnapshotRequest(StrictModel):
    selected_regime: Literal["OLD", "NEW"] | None = None


class ComputationApprovalRequest(StrictModel):
    decision: Literal["APPROVE", "REJECT"]
    justification: str = Field(min_length=8, max_length=3000)


class ToolCallRequest(StrictModel):
    name: Literal[
        "search_tax_law", "read_case_facts", "list_missing_information", "propose_fact",
        "explain_computation", "create_document_request_draft", "create_client_question_draft",
        "show_portal_guide", "compare_regimes", "summarise_discrepancies",
    ]
    arguments: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=160)


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=8000)


class DraftApprovalRequest(StrictModel):
    decision: Literal["APPROVE", "REJECT"]
    edited_text: str | None = Field(default=None, max_length=5000)


class ExportIdentityRequest(StrictModel):
    pan: str = Field(pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$")
    first_name: str
    middle_name: str = ""
    surname: str
    date_of_birth: date
    email: EmailStr
    mobile: str
    address: dict[str, Any]
    verification_place: str
    verification_capacity: str = "S"


class ExportCreateRequest(StrictModel):
    computation_run_id: str
    form_code: Literal["ITR_1", "ITR_2"]
    identity: ExportIdentityRequest
    intermediary_city: str
    schema_version: str = "V1.1"


class ExportApprovalRequest(StrictModel):
    decision: Literal["APPROVE", "REJECT"]
    justification: str = Field(min_length=8, max_length=3000)


class LegalSourceCreate(StrictModel):
    source_type: str
    title: str
    act_namespace: Literal["ITA_1961", "ITA_2025"]
    section_or_rule: str | None = None
    publication_date: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    applicable_periods: list[str] = Field(default_factory=list)
    official_url: str
    content_text: str = Field(min_length=20)
    review_status: Literal["PENDING", "APPROVED", "REJECTED"] = "PENDING"


class PrivacyRequestCreate(StrictModel):
    client_id: str
    request_type: Literal["ACCESS", "CORRECTION", "ERASURE", "CONSENT_WITHDRAWAL", "PORTABILITY"]
    note: str | None = Field(default=None, max_length=3000)


class ConsentCreate(StrictModel):
    client_id: str
    purpose_code: str
    notice_version: str
    status: Literal["GRANTED", "WITHDRAWN"]
    evidence: dict[str, Any] = Field(default_factory=dict)


class ReconciliationResolve(StrictModel):
    accepted_fact_id: str | None = None
    status: Literal["MATCHED", "PARTIAL_MATCH", "DIFFERENCE", "MISSING_IN_AIS", "MISSING_IN_CLIENT_DOCS", "DUPLICATE", "INFORMATION_ONLY", "REVIEW_REQUIRED", "RESOLVED"]
    resolution_note: str = Field(min_length=8, max_length=3000)


class FeatureFlagUpdate(StrictModel):
    enabled: bool
    config: dict[str, Any] = Field(default_factory=dict)

