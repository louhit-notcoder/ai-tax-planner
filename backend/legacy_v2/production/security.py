from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from .models import CA_ROLES


READ_ONLY_CA_ROLES = {"auditor", "document_operator"}
REVIEW_ROLES = {"firm_owner", "ca_partner", "ca_manager"}
PREPARATION_ROLES = REVIEW_ROLES | {"preparer"}


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str


def user_tenant_id(user: Any) -> str:
    value = getattr(user, "tenant_id", None)
    if value:
        return value
    # Legacy taxpayers are isolated in a personal tenant until assigned to a firm.
    return f"personal:{getattr(user, 'user_id')}"


def filing_tenant_id(filing: dict) -> str:
    return filing.get("tenant_id") or f"personal:{filing.get('user_id')}"


def can_access_filing(user: Any, filing: dict, *, write: bool = False, review: bool = False) -> AccessDecision:
    uid = getattr(user, "user_id")
    role = getattr(user, "role", "taxpayer")

    if filing.get("user_id") == uid:
        if review:
            return AccessDecision(False, "Taxpayer cannot perform reviewer action")
        if write and filing.get("locked"):
            return AccessDecision(False, "Case is locked")
        return AccessDecision(True, "Case owner")

    if role not in CA_ROLES:
        return AccessDecision(False, "User is not assigned to this case")

    assigned_ids = {
        filing.get("assigned_ca_id"),
        filing.get("assigned_preparer_id"),
        filing.get("assigned_reviewer_id"),
    }
    assigned_ids.update(filing.get("permitted_user_ids") or [])
    if uid not in assigned_ids:
        return AccessDecision(False, "CA user is not explicitly assigned to this case")

    if filing_tenant_id(filing) != user_tenant_id(user):
        return AccessDecision(False, "Cross-tenant access denied")

    if review and role not in REVIEW_ROLES:
        return AccessDecision(False, "Reviewer permission required")
    if write and role in READ_ONLY_CA_ROLES:
        return AccessDecision(False, "Role is read-only for this operation")
    if write and filing.get("locked"):
        return AccessDecision(False, "Case is locked")
    return AccessDecision(True, "Assigned case user")


def assert_filing_access(user: Any, filing: dict, *, write: bool = False, review: bool = False) -> None:
    decision = can_access_filing(user, filing, write=write, review=review)
    if not decision.allowed:
        status = 409 if decision.reason == "Case is locked" else 403
        raise HTTPException(status_code=status, detail=decision.reason)


def assert_document_access(user: Any, document: dict, filing: dict | None, *, write: bool = False) -> None:
    if filing is not None:
        assert_filing_access(user, filing, write=write)
        if document.get("filing_id") != filing.get("id"):
            raise HTTPException(status_code=403, detail="Document is not attached to the active case")
        return

    if document.get("user_id") != getattr(user, "user_id"):
        raise HTTPException(status_code=403, detail="Document access denied")


def permissions_for_role(role: str) -> frozenset[str]:
    base = {
        "tax_law:search",
        "case_facts:read",
        "case_missing_items:read",
        "computation:explain",
        "portal_guide:read",
        "regime_comparison:read",
        "discrepancy_summary:read",
    }
    if role in PREPARATION_ROLES:
        base |= {
            "fact_candidate:create",
            "document_request_draft:create",
            "client_question_draft:create",
        }
    return frozenset(base)
