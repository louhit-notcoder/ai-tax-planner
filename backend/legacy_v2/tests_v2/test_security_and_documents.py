from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from production.document_security import inspect_upload
from production.security import can_access_filing


def user(user_id, role="taxpayer", tenant_id=None):
    return SimpleNamespace(user_id=user_id, role=role, tenant_id=tenant_id)


def test_taxpayer_can_only_access_own_case():
    filing = {"id": "case", "user_id": "owner", "tenant_id": "personal:owner", "locked": False}
    assert can_access_filing(user("owner"), filing).allowed
    assert not can_access_filing(user("other"), filing).allowed


def test_unassigned_ca_cannot_access_case_even_with_ca_role():
    filing = {
        "id": "case",
        "user_id": "owner",
        "tenant_id": "firm:one",
        "assigned_ca_id": "ca-1",
        "assigned_preparer_id": None,
        "assigned_reviewer_id": None,
        "permitted_user_ids": [],
        "locked": False,
    }
    assert can_access_filing(user("ca-1", "ca_partner", "firm:one"), filing).allowed
    assert not can_access_filing(user("ca-2", "ca_partner", "firm:one"), filing).allowed


def test_cross_tenant_ca_access_is_denied():
    filing = {
        "id": "case",
        "user_id": "owner",
        "tenant_id": "firm:one",
        "assigned_ca_id": "ca-1",
        "assigned_preparer_id": None,
        "assigned_reviewer_id": None,
        "permitted_user_ids": [],
        "locked": False,
    }
    assert not can_access_filing(user("ca-1", "ca_partner", "firm:two"), filing).allowed


def test_locked_case_denies_write():
    filing = {"id": "case", "user_id": "owner", "tenant_id": "personal:owner", "locked": True}
    assert not can_access_filing(user("owner"), filing, write=True).allowed


def test_document_signature_validation_accepts_pdf():
    result = inspect_upload("form16.pdf", "application/pdf", b"%PDF-1.7\nmock")
    assert result.detected_kind == "pdf"
    assert len(result.sha256) == 64


def test_document_signature_validation_rejects_fake_pdf():
    with pytest.raises(HTTPException) as exc:
        inspect_upload("form16.pdf", "application/pdf", b"not-a-pdf")
    assert exc.value.status_code == 400


def test_document_extension_allowlist():
    with pytest.raises(HTTPException) as exc:
        inspect_upload("payload.exe", "application/octet-stream", b"MZ")
    assert exc.value.status_code == 415
