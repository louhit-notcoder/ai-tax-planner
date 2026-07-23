from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)
    sole_practitioner_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Membership(Base, TimestampMixin):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)


class Invitation(Base, TimestampMixin):
    __tablename__ = "invitations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    invited_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshSession(Base, TimestampMixin):
    __tablename__ = "refresh_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Client(Base, TimestampMixin):
    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("tenant_id", "pan_blind_index", name="uq_client_tenant_pan"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone_encrypted: Mapped[str | None] = mapped_column(Text)
    pan_encrypted: Mapped[str | None] = mapped_column(Text)
    pan_blind_index: Mapped[str | None] = mapped_column(String(128), index=True)
    date_of_birth_encrypted: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class TaxCase(Base, TimestampMixin):
    __tablename__ = "tax_cases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "client_id", "tax_period", name="uq_tax_case_period"),
        Index("ix_tax_case_tenant_status", "tenant_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True, nullable=False)
    tax_period: Mapped[str] = mapped_column(String(20), nullable=False)
    assessment_year: Mapped[str] = mapped_column(String(20), nullable=False)
    act_namespace: Mapped[str] = mapped_column(String(20), default="ITA_1961", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="INTAKE", nullable=False)
    selected_regime: Mapped[str] = mapped_column(String(10), default="NEW", nullable=False)
    recommended_form: Mapped[str | None] = mapped_column(String(20))
    rule_release_id: Mapped[str] = mapped_column(String(80), default="AY2026_27_V3.0.0", nullable=False)
    preparer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date | None] = mapped_column(Date)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    final_approval_id: Mapped[str | None] = mapped_column(String(36))
    risk_flags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class CaseAccess(Base, TimestampMixin):
    __tablename__ = "case_access"
    __table_args__ = (UniqueConstraint("case_id", "user_id", name="uq_case_access_user"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("tax_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    permission_level: Mapped[str] = mapped_column(String(30), default="EDIT", nullable=False)


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "case_id", "sha256", name="uq_document_case_hash"),
        Index("ix_document_tenant_case", "tenant_id", "case_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("tax_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(String(36))
    document_type: Mapped[str] = mapped_column(String(80), default="UNKNOWN", nullable=False)
    state: Mapped[str] = mapped_column(String(40), default="UPLOADED", nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_password_protected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    classification_confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))
    classification_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class DocumentVersion(Base, TimestampMixin):
    __tablename__ = "document_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    supersedes_version_id: Mapped[str | None] = mapped_column(ForeignKey("document_versions.id"))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class ExtractionRun(Base, TimestampMixin):
    __tablename__ = "extraction_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("tax_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    document_version_id: Mapped[str | None] = mapped_column(ForeignKey("document_versions.id"))
    adapter_code: Mapped[str] = mapped_column(String(100), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(40), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(40), default="RUNNING", nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvidenceClaim(Base, TimestampMixin):
    __tablename__ = "evidence_claims"
    __table_args__ = (Index("ix_evidence_case_field", "case_id", "field_code"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("tax_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    document_version_id: Mapped[str | None] = mapped_column(ForeignKey("document_versions.id"))
    extraction_run_id: Mapped[str] = mapped_column(ForeignKey("extraction_runs.id", ondelete="CASCADE"), index=True, nullable=False)
    field_code: Mapped[str] = mapped_column(String(160), nullable=False)
    value_type: Mapped[str] = mapped_column(String(30), nullable=False)
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    page_index: Mapped[int | None] = mapped_column(Integer)
    bounding_box: Mapped[list | None] = mapped_column(JSON)
    original_text: Mapped[str | None] = mapped_column(Text)
    crop_storage_key: Mapped[str | None] = mapped_column(String(1000))
    extraction_method: Mapped[str] = mapped_column(String(80), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))
    validation_results: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="EXTRACTED", nullable=False)


class CandidateFact(Base, TimestampMixin):
    __tablename__ = "candidate_facts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_candidate_idempotency"),
        Index("ix_candidate_case_status", "case_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("tax_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    field_code: Mapped[str] = mapped_column(String(160), nullable=False)
    value_type: Mapped[str] = mapped_column(String(30), nullable=False)
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    tax_period: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_claim_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="PENDING_REVIEW", nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="DOCUMENT", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    proposed_by: Mapped[str | None] = mapped_column(String(36))
    model_explanation: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_justification: Mapped[str | None] = mapped_column(Text)


class CanonicalFact(Base, TimestampMixin):
    __tablename__ = "canonical_facts"
    __table_args__ = (
        UniqueConstraint("case_id", "field_code", "entity_key", "version", name="uq_fact_version"),
        Index("ix_canonical_case_current", "case_id", "is_current"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("tax_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    field_code: Mapped[str] = mapped_column(String(160), nullable=False)
    entity_key: Mapped[str] = mapped_column(String(160), default="ROOT", nullable=False)
    value_type: Mapped[str] = mapped_column(String(30), nullable=False)
    value_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    tax_period: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_claim_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    source_candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidate_facts.id"))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approved_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    superseded_by_id: Mapped[str | None] = mapped_column(ForeignKey("canonical_facts.id"))


class FactSnapshot(Base, TimestampMixin):
    __tablename__ = "fact_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("tax_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    facts_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    immutable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RuleRelease(Base, TimestampMixin):
    __tablename__ = "rule_releases"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), index=True)
    tax_period: Mapped[str] = mapped_column(String(20), nullable=False)
    assessment_year: Mapped[str] = mapped_column(String(20), nullable=False)
    act_namespace: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    rules_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    rules_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_documents: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    code_commit: Mapped[str | None] = mapped_column(String(80))
    reviewed_by: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ComputationRun(Base, TimestampMixin):
    __tablename__ = "computation_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("tax_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    fact_snapshot_id: Mapped[str] = mapped_column(ForeignKey("fact_snapshots.id"), nullable=False)
    rule_release_id: Mapped[str] = mapped_column(ForeignKey("rule_releases.id"), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(50), nullable=False)
    regime: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    immutable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CalculationLineRecord(Base, TimestampMixin):
    __tablename__ = "calculation_lines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    computation_run_id: Mapped[str] = mapped_column(ForeignKey("computation_runs.id", ondelete="CASCADE"), index=True, nullable=False)
    line_order: Mapped[int] = mapped_column(Integer, nullable=False)
    line_code: Mapped[str] = mapped_column(String(160), nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    formula: Mapped[str] = mapped_column(Text, nullable=False)
    input_fact_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    input_line_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rule_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    amount_json: Mapped[dict] = mapped_column(JSON, nullable=False)


class ReconciliationItem(Base, TimestampMixin):
    __tablename__ = "reconciliation_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("tax_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_key: Mapped[str] = mapped_column(String(160), default="ROOT", nullable=False)
    source_values: Mapped[dict] = mapped_column(JSON, nullable=False)
    accepted_fact_id: Mapped[str | None] = mapped_column(ForeignKey("canonical_facts.id"))
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    difference_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MissingItem(Base, TimestampMixin):
    __tablename__ = "missing_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("tax_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="OPEN", nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClientQuestionDraft(Base, TimestampMixin):
    __tablename__ = "client_question_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("tax_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    topic: Mapped[str] = mapped_column(String(120), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentRequestDraft(Base, TimestampMixin):
    __tablename__ = "document_request_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("tax_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    document_type: Mapped[str] = mapped_column(String(120), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    deadline: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Approval(Base, TimestampMixin):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("tax_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    approval_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(80), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ExportSnapshot(Base, TimestampMixin):
    __tablename__ = "export_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("tax_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    computation_run_id: Mapped[str] = mapped_column(ForeignKey("computation_runs.id"), nullable=False)
    form_code: Mapped[str] = mapped_column(String(20), nullable=False)
    assessment_year: Mapped[str] = mapped_column(String(20), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    validation_version: Mapped[str] = mapped_column(String(40), nullable=False)
    exporter_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    immutable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LegalSource(Base, TimestampMixin):
    __tablename__ = "legal_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    act_namespace: Mapped[str] = mapped_column(String(20), nullable=False)
    section_or_rule: Mapped[str | None] = mapped_column(String(120))
    publication_date: Mapped[date | None] = mapped_column(Date)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    applicable_periods: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    official_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_document_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_location: Mapped[str | None] = mapped_column(String(300))
    review_status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    superseded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_json: Mapped[list | None] = mapped_column(JSON)
    embedding_model: Mapped[str | None] = mapped_column(String(200))


class PrivacyRequest(Base, TimestampMixin):
    __tablename__ = "privacy_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True, nullable=False)
    request_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="OPEN", nullable=False)
    requested_by: Mapped[str] = mapped_column(String(36), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completion_note: Mapped[str | None] = mapped_column(Text)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    case_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(80))
    before_hash: Mapped[str | None] = mapped_column(String(64))
    after_hash: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

class BackgroundJob(Base, TimestampMixin):
    __tablename__ = "background_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    case_id: Mapped[str | None] = mapped_column(String(36), index=True)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="QUEUED", nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class FeatureFlag(Base, TimestampMixin):
    __tablename__ = "feature_flags"
    __table_args__ = (UniqueConstraint("tenant_id", "flag_key", name="uq_feature_flag_tenant_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), index=True)
    flag_key: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(36))


class ConsentRecord(Base, TimestampMixin):
    __tablename__ = "consent_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    client_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    purpose_code: Mapped[str] = mapped_column(String(120), nullable=False)
    notice_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    captured_by: Mapped[str] = mapped_column(String(36), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class SecurityEvent(Base):
    __tablename__ = "security_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    details_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class ModelEvaluationRun(Base, TimestampMixin):
    __tablename__ = "model_evaluation_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    suite_version: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    approved_for_production: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(36))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatMessage(Base, TimestampMixin):
    """Persisted per-case conversation between the CA and the tax assistant.

    Each row is one turn. `tool_trace` records any server-controlled tool calls the
    model made on that turn (name + result type only) so the workspace can show what
    the assistant did without trusting free-text claims.
    """

    __tablename__ = "chat_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("tax_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tool_trace: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (Index("ix_chat_messages_case_created", "case_id", "created_at"),)


class DocumentPassword(Base, TimestampMixin):
    """Encrypted store of working PDF passwords, scoped to a case.

    Passwords are encrypted at rest (never stored in plaintext) and reused to
    auto-unlock sibling documents in the same case, so the CA is asked at most
    once per distinct password.
    """

    __tablename__ = "document_passwords"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("tax_cases.id", ondelete="CASCADE"), index=True, nullable=False)
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36))
