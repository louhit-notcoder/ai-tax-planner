from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import fitz
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db_models import LegalSource
from app.document_adapters.ais import AISJSONAdapter
from app.document_adapters.brokers import BrokerCapitalGainsAdapter
from app.document_adapters.form16 import Form16Adapter
from app.itr.exporter import ExportRequest, ITRIdentity, SchemaDrivenITRExporter
from app.itr.schema_registry import OfficialSchemaRegistry
from app.legal.retrieval import search_approved_sources
from app.tax_engine import DeterministicTaxEngine, load_rule_release
from app.tax_engine.models import (
    ComputationStatus,
    EmploymentIncome,
    Regime,
    SalaryComponent,
    TaxFactSnapshot,
    TaxpayerProfile,
)


def _form16_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(
        fitz.Rect(50, 50, 540, 760),
        """FORM NO. 16\nCertificate under section 203\nPART B\nName and address of the Employer: Example Technologies Private Limited\nTAN of the Deductor: ABCD12345E\nGross Salary 14,51,200\nTotal amount of exemption claimed under section 10 60,000\nProfessional tax 2,400\nTotal amount of tax deducted 1,05,000\n""",
        fontsize=11,
    )
    return document.tobytes()


def test_form16_adapter_creates_evidence_linked_claims():
    adapter = Form16Adapter()
    content = _form16_pdf()
    assert adapter.supports("form16.pdf", "application/pdf", content) >= 0.50
    result = adapter.extract("form16.pdf", "application/pdf", content)
    by_code = {claim.field_code: claim for claim in result.claims}
    assert by_code["SALARY.GROSS"].value["amount"] == "1451200.00"
    assert by_code["TAX_PAYMENT.TDS.SALARY"].value["amount"] == "105000.00"
    assert by_code["SALARY.GROSS"].source.page_index == 0
    assert by_code["SALARY.GROSS"].source.bounding_box


def test_ais_adapter_deduplicates_transaction_records():
    payload = {
        "records": [
            {
                "informationCode": "SALARY",
                "informationDescription": "Salary",
                "reportingEntityName": "Example Employer",
                "transactionId": "TX-1",
                "derivedValue": "100000",
            },
            {
                "informationCode": "SALARY",
                "informationDescription": "Salary",
                "reportingEntityName": "Example Employer",
                "transactionId": "TX-1",
                "derivedValue": "100000",
            },
        ]
    }
    result = AISJSONAdapter().extract("ais.json", "application/json", json.dumps(payload).encode())
    assert len(result.claims) == 1
    assert result.metadata["accepted_count"] == 1
    assert result.claims[0].value["amount"] == "100000.00"


def test_broker_adapter_outputs_transaction_level_claims():
    content = (
        "Symbol,Buy Date,Sell Date,Sale Value,Buy Value,Transfer Expenses,STT Paid\n"
        "ABC LTD,01-01-2024,01-06-2025,500000,200000,1000,Yes\n"
    ).encode()
    result = BrokerCapitalGainsAdapter().extract("zerodha-capital-gains.csv", "text/csv", content)
    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.field_code == "CAPITAL_GAIN.TRANSACTION"
    assert claim.value["sale_consideration"] == "500000"
    assert claim.value["actual_cost"] == "200000"
    assert claim.value["stt_paid_on_transfer"] is True


def _write_test_schema(root: Path) -> OfficialSchemaRegistry:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["ITR"],
        "properties": {
            "ITR": {
                "type": "object",
                "required": ["ITR1"],
                "properties": {
                    "ITR1": {"type": "object", "additionalProperties": True}
                },
                "additionalProperties": False,
            }
        },
        "additionalProperties": False,
    }
    schema_bytes = json.dumps(schema, sort_keys=True).encode()
    filename = "ITR_1_test_schema.json"
    (root / filename).write_bytes(schema_bytes)
    manifest = {
        "artifacts": {
            "ITR_1": {
                "filename": filename,
                "version": "TEST-1",
                "sha256": hashlib.sha256(schema_bytes).hexdigest(),
                "source_url": "https://www.incometax.gov.in/test-schema",
            }
        }
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return OfficialSchemaRegistry(root)


def _complete_computation():
    facts = TaxFactSnapshot(
        snapshot_id="export-facts",
        case_id="export-case",
        selected_regime=Regime.NEW,
        profile=TaxpayerProfile(date_of_birth=date(1990, 1, 1)),
        employments=[
            EmploymentIncome(
                employment_id="EMP-1",
                employer_name="Example Employer",
                components=[SalaryComponent(code="GROSS", label="Gross salary", amount="500000")],
            )
        ],
        approved_fact_ids=["FACT-1"],
    )
    result = DeterministicTaxEngine().compute(facts, load_rule_release("AY2026_27_V3.0.0"))
    assert result.status == ComputationStatus.COMPLETE
    return facts, result


def _identity():
    return ITRIdentity(
        pan="ABCDE1234F",
        first_name="Test",
        surname="Taxpayer",
        date_of_birth=date(1990, 1, 1),
        email="taxpayer@example.com",
        mobile="9999999999",
        address={"ResidenceNo": "1", "ResidenceName": "Test"},
        verification_place="Mumbai",
    )


def test_schema_driven_export_is_reproducible_for_explicit_creation_date(tmp_path):
    registry = _write_test_schema(tmp_path)
    facts, computation = _complete_computation()
    exporter = SchemaDrivenITRExporter(registry)
    request = ExportRequest(
        form_code="ITR_1",
        identity=_identity(),
        computation=computation,
        facts=facts,
        intermediary_city="Mumbai",
        creation_date=date(2026, 7, 21),
        ca_reviewer_approved=True,
    )
    first = exporter.build(request)
    second = exporter.build(request)
    assert first.status == "READY_FOR_CA_REVIEW"
    assert first.validation_errors == []
    assert first.snapshot_hash == second.snapshot_hash
    assert first.payload == second.payload


def test_exporter_rejects_provisional_computation(tmp_path):
    registry = _write_test_schema(tmp_path)
    facts, computation = _complete_computation()
    provisional = computation.model_copy(update={"status": ComputationStatus.PROVISIONAL})
    exporter = SchemaDrivenITRExporter(registry)
    with pytest.raises(ValueError, match="Only COMPLETE"):
        exporter.build(ExportRequest(
            form_code="ITR_1",
            identity=_identity(),
            computation=provisional,
            facts=facts,
            intermediary_city="Mumbai",
            creation_date=date(2026, 7, 21),
            ca_reviewer_approved=True,
        ))


def test_legal_retrieval_returns_only_approved_applicable_official_sources():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    LegalSource.__table__.create(engine)
    with Session(engine) as db:
        db.add_all([
            LegalSource(
                source_type="ACT",
                title="Income-tax Act section 87A",
                act_namespace="ITA_1961",
                section_or_rule="87A",
                applicable_periods=["AY 2026-27"],
                official_url="https://www.incometax.gov.in/official-87a",
                source_hash="a" * 64,
                review_status="APPROVED",
                content_text="Rebate under section 87A for an eligible resident individual.",
            ),
            LegalSource(
                source_type="BLOG",
                title="Unreviewed rebate commentary",
                act_namespace="ITA_1961",
                section_or_rule="87A",
                applicable_periods=["AY 2026-27"],
                official_url="https://example.invalid/blog",
                source_hash="b" * 64,
                review_status="PENDING",
                content_text="Rebate under section 87A.",
            ),
        ])
        db.commit()
        results = search_approved_sources(
            db,
            query="section 87A rebate",
            tax_period="AY 2026-27",
            act_namespace="ITA_1961",
        )
    assert len(results) == 1
    assert results[0].title == "Income-tax Act section 87A"
    assert results[0].official_url.startswith("https://www.incometax.gov.in/")
