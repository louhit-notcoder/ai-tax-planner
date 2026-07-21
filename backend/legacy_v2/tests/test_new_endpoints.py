"""Regression tests for iteration-2 production features:
- multi-file consolidated parse (/filings/{fid}/parse-documents)
- real AIS decryption + reconciliation (/filings/{fid}/upload-ais)
- plain AIS acceptance
- reconcile-without-AIS returns 400
- computation PDF export
- document info / page render / locate for CA desk
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000").rstrip("/")
TAX_TOKEN = os.environ.get("LEGACY_TAXPAYER_TOKEN", "")
CA_TOKEN = os.environ.get("LEGACY_CA_TOKEN", "")
FORM16 = "/app/test_data/form16_sample.pdf"
AIS_ENC = "/app/test_data/ais_encrypted_sample.json"
AIS_PLAIN = "/app/test_data/ais_plain_sample.json"


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def filing_id():
    """Create a fresh filing seeded with baseline income data."""
    r = requests.post(f"{BASE_URL}/api/filings", headers=_headers(TAX_TOKEN),
                      json={"assessment_year": "AY 2026-27"})
    assert r.status_code == 200
    fid = r.json()["id"]
    # seed baseline that matches form16_sample gross_salary 1450000
    requests.put(f"{BASE_URL}/api/filings/{fid}", headers=_headers(TAX_TOKEN),
                 json={"parsed_payload": {"gross_salary": 1450000, "tds_deducted": 105000,
                                          "other_income": 0, "deductions_80c": 150000}})
    return fid


@pytest.fixture(scope="module")
def uploaded_doc_ids(filing_id):
    """Upload the form16 sample TWICE to test multi-doc consolidation."""
    ids = []
    for i in range(2):
        with open(FORM16, "rb") as fh:
            files = {"file": (f"form16_{i}.pdf", fh, "application/pdf")}
            data = {"document_type": "form_16", "filing_id": filing_id}
            r = requests.post(f"{BASE_URL}/api/documents/upload",
                              headers=_headers(TAX_TOKEN), files=files, data=data)
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])
    return ids


class TestParseDocuments:
    def test_parse_documents_consolidated(self, filing_id, uploaded_doc_ids):
        r = requests.post(f"{BASE_URL}/api/filings/{filing_id}/parse-documents",
                          headers=_headers(TAX_TOKEN), timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "parsed_json" in d
        assert d["documents_analyzed"] == 2
        parsed = d["parsed_json"]
        # gross salary should be around 1,450,000 from the sample form 16
        assert parsed.get("gross_salary", 0) >= 100000, f"expected salary parsed, got {parsed.get('gross_salary')}"

    def test_filing_merged_after_parse(self, filing_id):
        r = requests.get(f"{BASE_URL}/api/filings/{filing_id}", headers=_headers(TAX_TOKEN))
        assert r.status_code == 200
        payload = r.json()["parsed_payload"]
        assert payload.get("gross_salary", 0) > 0


class TestReconcile:
    def test_reconcile_without_ais_returns_400(self):
        # brand-new filing without AIS
        r = requests.post(f"{BASE_URL}/api/filings", headers=_headers(TAX_TOKEN),
                          json={"assessment_year": "AY 2026-27"})
        fid = r.json()["id"]
        r2 = requests.post(f"{BASE_URL}/api/filings/{fid}/reconcile",
                           headers=_headers(TAX_TOKEN))
        assert r2.status_code == 400
        assert "AIS" in r2.json()["detail"]

    def test_upload_encrypted_ais_decrypts_and_flags(self, filing_id):
        with open(AIS_ENC, "rb") as fh:
            files = {"file": ("ais.json", fh, "application/json")}
            data = {"pan": "ABCDE1234F", "dob": "15061990"}
            r = requests.post(f"{BASE_URL}/api/filings/{filing_id}/upload-ais",
                              headers=_headers(TAX_TOKEN), files=files, data=data)
        assert r.status_code == 200, r.text
        d = r.json()
        prefill = d["ais_prefill"]
        # AIS salary 1451200, dividend 45000, interest 18500, tds 105000
        assert prefill["gross_salary"] == 1451200.0
        assert prefill["dividend"] == 45000.0
        assert prefill["savings_interest"] == 18500.0
        assert prefill["tds_deducted"] == 105000.0
        assert prefill["other_income"] == 63500.0
        fields = {f["field"]: f["severity"] for f in d["discrepancies"]}
        # form salary 1450000 vs AIS 1451200 => salary variance HIGH
        assert fields.get("gross_salary") == "HIGH"
        # other_income 0 vs AIS 63500 => other_income MEDIUM
        assert fields.get("other_income") == "MEDIUM"

    def test_upload_plain_ais_accepted(self):
        # separate filing to avoid state pollution
        r = requests.post(f"{BASE_URL}/api/filings", headers=_headers(TAX_TOKEN),
                          json={"assessment_year": "AY 2026-27"})
        fid = r.json()["id"]
        requests.put(f"{BASE_URL}/api/filings/{fid}", headers=_headers(TAX_TOKEN),
                     json={"parsed_payload": {"gross_salary": 1450000, "tds_deducted": 105000}})
        with open(AIS_PLAIN, "rb") as fh:
            files = {"file": ("ais.json", fh, "application/json")}
            data = {"pan": "ABCDE1234F", "dob": "15061990"}
            r = requests.post(f"{BASE_URL}/api/filings/{fid}/upload-ais",
                              headers=_headers(TAX_TOKEN), files=files, data=data)
        assert r.status_code == 200, r.text
        prefill = r.json()["ais_prefill"]
        assert prefill["gross_salary"] == 1451200.0

    def test_reconcile_after_ais(self, filing_id):
        r = requests.post(f"{BASE_URL}/api/filings/{filing_id}/reconcile",
                          headers=_headers(TAX_TOKEN))
        assert r.status_code == 200
        assert "discrepancies" in r.json()


class TestComputationPdf:
    def test_taxpayer_download_pdf(self, filing_id):
        r = requests.get(f"{BASE_URL}/api/filings/{filing_id}/computation-pdf",
                         headers=_headers(TAX_TOKEN))
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:4] == b"%PDF"

    def test_ca_download_pdf(self, filing_id):
        # ensure filing is under this CA (request verification first)
        requests.post(f"{BASE_URL}/api/filings/{filing_id}/request-verification",
                      headers=_headers(TAX_TOKEN))
        r = requests.get(f"{BASE_URL}/api/filings/{filing_id}/computation-pdf",
                         headers=_headers(CA_TOKEN))
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"


class TestDocumentRenderAndLocate:
    def test_document_info_pdf(self, uploaded_doc_ids):
        did = uploaded_doc_ids[0]
        r = requests.get(f"{BASE_URL}/api/documents/{did}/info",
                         headers=_headers(CA_TOKEN))
        assert r.status_code == 200
        d = r.json()
        assert d["is_pdf"] is True
        assert d["page_count"] >= 1

    def test_document_page_png(self, uploaded_doc_ids):
        did = uploaded_doc_ids[0]
        r = requests.get(f"{BASE_URL}/api/documents/{did}/page/0",
                         headers=_headers(CA_TOKEN))
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        # PNG magic number
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_document_locate_indian_grouped(self, uploaded_doc_ids):
        did = uploaded_doc_ids[0]
        r = requests.post(f"{BASE_URL}/api/documents/{did}/locate",
                          headers=_headers(CA_TOKEN),
                          json={"term": "1450000"})
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d["rects"], list)
        # should match indian-grouped "14,50,000"
        if d["rects"]:
            assert d["matched"] in ("14,50,000", "1450000", "1,450,000")
            assert len(d["rects"]) >= 1
