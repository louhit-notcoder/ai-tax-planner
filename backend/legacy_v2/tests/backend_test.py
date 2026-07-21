"""Green Papaya backend API regression tests.

Covers auth, filings CRUD/compute/reconcile/lock/export, documents upload/parse,
CA console (link, triage, stats, override, audit).
"""
import os
import io
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000").rstrip("/")
TAX_TOKEN = os.environ.get("LEGACY_TAXPAYER_TOKEN", "")
CA_TOKEN = os.environ.get("LEGACY_CA_TOKEN", "")
FORM16_PATH = "/tmp/form16_test.pdf"


def _c(token=None):
    s = requests.Session()
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def tax(): return _c(TAX_TOKEN)


@pytest.fixture(scope="module")
def ca(): return _c(CA_TOKEN)


# -------------------- Auth --------------------
class TestAuth:
    def test_me_taxpayer(self, tax):
        r = tax.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        d = r.json()
        assert d["role"] == "taxpayer"
        assert d["user_id"] == "user_taxpayerdemo"

    def test_me_ca(self, ca):
        r = ca.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 200
        assert r.json()["role"] == "ca_partner"

    def test_me_unauth(self):
        r = requests.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401

    def test_ca_endpoint_forbidden_for_taxpayer(self, tax):
        r = tax.get(f"{BASE_URL}/api/ca/triage")
        assert r.status_code == 403


# -------------------- Filing CRUD & compute --------------------
class TestFilings:
    filing_id = None

    def test_create_filing(self, tax):
        r = tax.post(f"{BASE_URL}/api/filings", json={"assessment_year": "AY 2026-27"})
        assert r.status_code == 200
        d = r.json()
        assert d["user_id"] == "user_taxpayerdemo"
        assert d["selected_regime"] == "NEW"
        assert d["status"] == "not_started"
        TestFilings.filing_id = d["id"]

    def test_list_filings(self, tax):
        r = tax.get(f"{BASE_URL}/api/filings")
        assert r.status_code == 200
        ids = [f["id"] for f in r.json()]
        assert TestFilings.filing_id in ids

    def test_update_income_and_compute(self, tax):
        fid = TestFilings.filing_id
        payload = {"parsed_payload": {
            "gross_salary": 1500000, "section_10_exemptions": 60000,
            "deductions_80c": 150000, "deductions_80d": 25000,
            "tds_deducted": 220000, "other_income": 0,
        }}
        r = tax.put(f"{BASE_URL}/api/filings/{fid}", json=payload)
        assert r.status_code == 200
        d = r.json()
        assert d["parsed_payload"]["gross_salary"] == 1500000
        comp = d["tax_computation_summary"]
        assert comp is not None
        assert "tax_liability_old" in comp and "tax_liability_new" in comp
        assert comp["recommended_regime"] in ("OLD", "NEW")

    def test_recompute(self, tax):
        fid = TestFilings.filing_id
        r = tax.post(f"{BASE_URL}/api/filings/{fid}/compute")
        assert r.status_code == 200
        d = r.json()
        assert d["tax_liability_new"] > 0

    def test_regime_toggle(self, tax):
        fid = TestFilings.filing_id
        r = tax.put(f"{BASE_URL}/api/filings/{fid}", json={"selected_regime": "OLD"})
        assert r.status_code == 200
        assert r.json()["selected_regime"] == "OLD"

    def test_reconcile_flags(self, tax):
        fid = TestFilings.filing_id
        r = tax.post(f"{BASE_URL}/api/filings/{fid}/reconcile")
        # iteration-2: /reconcile now requires AIS uploaded first -> 400
        assert r.status_code == 400
        assert "AIS" in r.json()["detail"]

    def test_request_verification_assigns_ca(self, tax):
        fid = TestFilings.filing_id
        r = tax.post(f"{BASE_URL}/api/filings/{fid}/request-verification")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "under_review"
        assert d["assigned_ca_id"] == "user_cademo"

    def test_export_json(self, tax):
        fid = TestFilings.filing_id
        r = tax.get(f"{BASE_URL}/api/filings/{fid}/export-json")
        assert r.status_code == 200
        d = r.json()
        assert "ITR" in d
        assert "ITR1_ITR2" in d["ITR"]


# -------------------- Documents --------------------
class TestDocuments:
    doc_id = None

    def test_upload_pdf(self, tax):
        assert os.path.exists(FORM16_PATH), "Form 16 test PDF missing"
        with open(FORM16_PATH, "rb") as f:
            files = {"file": ("form16_test.pdf", f, "application/pdf")}
            data = {"document_type": "form_16", "filing_id": TestFilings.filing_id or ""}
            # session lacks the json content-type header now
            s = requests.Session()
            s.headers.update({"Authorization": f"Bearer {TAX_TOKEN}"})
            r = s.post(f"{BASE_URL}/api/documents/upload", files=files, data=data)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["file_name"] == "form16_test.pdf"
        TestDocuments.doc_id = d["id"]

    def test_list_documents(self, tax):
        r = tax.get(f"{BASE_URL}/api/documents")
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
        assert TestDocuments.doc_id in ids

    def test_parse_document(self, tax):
        did = TestDocuments.doc_id
        r = tax.post(f"{BASE_URL}/api/documents/{did}/parse", timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "parsed_json" in d
        # Confidence should be present
        assert "confidence_score" in d


# -------------------- CA console --------------------
class TestCA:
    def test_ca_stats(self, ca):
        r = ca.get(f"{BASE_URL}/api/ca/stats")
        assert r.status_code == 200
        d = r.json()
        assert "clients" in d and d["clients"] >= 1
        assert "total_filings" in d

    def test_ca_triage(self, ca):
        r = ca.get(f"{BASE_URL}/api/ca/triage")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_ca_clients(self, ca):
        r = ca.get(f"{BASE_URL}/api/ca/clients")
        assert r.status_code == 200
        d = r.json()
        assert len(d) >= 1

    def test_override_requires_justification(self, ca):
        fid = TestFilings.filing_id
        r = ca.post(f"{BASE_URL}/api/validation/override-field", json={
            "state_id": fid, "target_field": "gross_salary",
            "new_value": 1501200, "justification": "  "
        })
        assert r.status_code == 400

    def test_override_success_creates_audit(self, ca):
        fid = TestFilings.filing_id
        r = ca.post(f"{BASE_URL}/api/validation/override-field", json={
            "state_id": fid, "target_field": "gross_salary",
            "new_value": 1501200, "justification": "AIS variance reconciled to ITD figures."
        })
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "success"
        # verify audit log
        r2 = ca.get(f"{BASE_URL}/api/filings/{fid}/audit-logs")
        assert r2.status_code == 200
        logs = r2.json()
        assert any(l.get("modified_field") == "gross_salary" for l in logs)

    def test_ca_audit_logs(self, ca):
        r = ca.get(f"{BASE_URL}/api/ca/audit-logs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) >= 1

    def test_lock_filing(self, ca):
        fid = TestFilings.filing_id
        r = ca.post(f"{BASE_URL}/api/filings/{fid}/lock")
        assert r.status_code == 200
        d = r.json()
        assert d["locked"] is True
        assert d["status"] == "json_generated"
        assert d["itd_json"] is not None

    def test_locked_filing_rejects_updates(self, tax):
        fid = TestFilings.filing_id
        r = tax.put(f"{BASE_URL}/api/filings/{fid}", json={"selected_regime": "NEW"})
        assert r.status_code == 400

    def test_link_client_not_found(self, ca):
        r = ca.post(f"{BASE_URL}/api/ca/link-client", json={"client_email": "nobody@nowhere.test"})
        assert r.status_code == 404

    def test_link_client_success(self, ca):
        r = ca.post(f"{BASE_URL}/api/ca/link-client", json={"client_email": "taxpayer.demo@greenpapaya.test"})
        assert r.status_code == 200
        assert r.json()["client_id"] == "user_taxpayerdemo"
