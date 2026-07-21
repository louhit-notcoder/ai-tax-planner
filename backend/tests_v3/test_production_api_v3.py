import os
from pathlib import Path

DB = Path('/tmp/green_papaya_v3_test.db')
if DB.exists():
    DB.unlink()
os.environ['GREEN_PAPAYA_ENV'] = 'development'
os.environ['DATABASE_URL'] = f'sqlite:///{DB}'
os.environ['REQUIRE_MFA_FOR_PRIVILEGED_ROLES'] = 'false'
os.environ['ALLOW_DEV_BOOTSTRAP'] = 'true'
os.environ['LOCAL_STORAGE_ROOT'] = '/tmp/gp-v3-storage'
os.environ['MALWARE_SCAN_REQUIRED'] = 'false'

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, Base, engine
from app.db_models import ClientQuestionDraft, DocumentRequestDraft, Tenant, User, Membership, Client as DBClient, TaxCase
from app.security import Actor, assert_case_access, hash_password
from sqlalchemy import select
from fastapi import HTTPException
import pytest


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def bootstrap(client):
    response = client.post('/api/auth/bootstrap', json={
        'firm_name': 'Test CA Firm', 'firm_slug': 'test-ca-firm', 'owner_name': 'Owner User',
        'owner_email': 'owner@example.com', 'password': 'VerySecurePassword123!'
    })
    assert response.status_code == 201, response.text
    return response.json()['access_token']


def headers(token):
    return {'Authorization': f'Bearer {token}'}


def create_case(client, token):
    r = client.post('/api/clients', headers=headers(token), json={'display_name': 'Test Taxpayer', 'email': 'taxpayer@example.com', 'pan': 'ABCDE1234F', 'date_of_birth': '1990-01-01'})
    assert r.status_code == 201, r.text
    client_id = r.json()['id']
    r = client.post('/api/cases', headers=headers(token), json={'client_id': client_id, 'tax_period': 'FY 2025-26', 'assessment_year': 'AY 2026-27', 'selected_regime': 'NEW'})
    assert r.status_code == 201, r.text
    return r.json()['id']


def accept_fact(client, token, case_id, field_code, value, entity_key='ROOT', value_type='object', key='manual-key'):
    r = client.post(f'/api/cases/{case_id}/candidate-facts', headers=headers(token), json={
        'field_code': field_code, 'entity_key': entity_key, 'value_type': value_type,
        'value': value, 'evidence_claim_ids': [], 'idempotency_key': key,
    })
    assert r.status_code == 201, r.text
    candidate_id = r.json()['id']
    r = client.post(f'/api/candidate-facts/{candidate_id}/review', headers=headers(token), json={'decision': 'ACCEPT', 'justification': 'Verified against original records and approved for testing.'})
    assert r.status_code == 200, r.text
    return r.json()['canonical_fact_id']


def test_end_to_end_salary_computation_and_approval():
    with TestClient(app) as client:
        token = bootstrap(client)
        case_id = create_case(client, token)
        accept_fact(client, token, case_id, 'SALARY.EMPLOYMENT', {
            'employment_id': 'EMP1', 'employer_name': 'Example Pvt Ltd',
            'components': [{'code': 'GROSS', 'label': 'Gross salary', 'amount': '1275000', 'exempt_under_section_10': '0', 'evidence_fact_ids': []}],
            'professional_tax': '0', 'employer_tds': '0', 'is_pension': False, 'is_family_pension': False, 'evidence_fact_ids': []
        }, entity_key='EMP1', key='salary-1')
        r = client.post(f'/api/cases/{case_id}/computations', headers=headers(token), json={'selected_regime': 'NEW'})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body['status'] == 'COMPLETE'
        selected = body['result']['selected_result']
        assert selected['total_income'] == '1200000.00'
        assert selected['total_tax_liability'] == '0.00'
        assert body['result']['new_regime']['rebate_87a'] == '60000.00'
        run_id = body['id']
        r = client.post(f'/api/computations/{run_id}/review', headers=headers(token), json={'decision': 'APPROVE', 'justification': 'Exact result reviewed against the approved golden case.'})
        assert r.status_code == 200, r.text
        assert r.json()['approved_by']


def test_ai_drafts_are_persisted_and_idempotent():
    with TestClient(app) as client:
        token = bootstrap(client)
        case_id = create_case(client, token)
        call = {'name': 'create_client_question_draft', 'arguments': {'topic': 'property_sale', 'question': 'Was any property sold during FY 2025-26?', 'context': 'Needed to determine capital-gains reporting.', 'priority': 'HIGH'}, 'idempotency_key': 'question-draft-001'}
        first = client.post(f'/api/cases/{case_id}/assistant/tools', headers=headers(token), json=call)
        second = client.post(f'/api/cases/{case_id}/assistant/tools', headers=headers(token), json=call)
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json()['draft_id'] == second.json()['draft_id']
        listing = client.get(f'/api/cases/{case_id}/assistant/drafts', headers=headers(token))
        assert len(listing.json()['client_questions']) == 1


def test_house_property_and_capital_gain_are_included():
    with TestClient(app) as client:
        token = bootstrap(client)
        case_id = create_case(client, token)
        accept_fact(client, token, case_id, 'HOUSE_PROPERTY', {
            'property_id': 'P1', 'ownership_percentage': '100', 'occupancy_type': 'LET_OUT',
            'gross_annual_value': '300000', 'municipal_taxes_paid': '20000', 'unrealised_rent': '0',
            'interest_on_borrowed_capital': '50000', 'pre_construction_interest_installment': '0', 'evidence_fact_ids': []
        }, entity_key='P1', key='property-1')
        accept_fact(client, token, case_id, 'CAPITAL_GAIN.TRANSACTION', {
            'transaction_id': 'T1', 'asset_type': 'LISTED_EQUITY', 'description': 'Listed shares',
            'acquisition_date': '2024-01-01', 'transfer_date': '2025-06-01', 'sale_consideration': '500000',
            'transfer_expenses': '0', 'actual_cost': '200000', 'improvement_cost': '0',
            'stt_paid_on_acquisition': True, 'stt_paid_on_transfer': True, 'listed': True, 'evidence_fact_ids': []
        }, entity_key='T1', key='capital-1')
        r = client.post(f'/api/cases/{case_id}/computations', headers=headers(token), json={'selected_regime': 'NEW'})
        assert r.status_code == 201, r.text
        result = r.json()['result']
        assert result['status'] == 'PROVISIONAL'
        assert any(bucket['code'] == 'SECTION_112A' and bucket['gross_amount'] == '300000.00' for bucket in result['buckets'])
        assert result['selected_result']['gross_total_income'] != '0.00'


def test_export_is_fail_closed_without_pinned_schema_and_utility():
    with TestClient(app) as client:
        token = bootstrap(client)
        case_id = create_case(client, token)
        accept_fact(client, token, case_id, 'SALARY.EMPLOYMENT', {
            'employment_id': 'EMP1', 'employer_name': 'Example Pvt Ltd',
            'components': [{'code': 'GROSS', 'label': 'Gross salary', 'amount': '500000', 'exempt_under_section_10': '0', 'evidence_fact_ids': []}],
            'professional_tax': '0', 'employer_tds': '0', 'is_pension': False, 'is_family_pension': False, 'evidence_fact_ids': []
        }, entity_key='EMP1', key='salary-export')
        comp = client.post(f'/api/cases/{case_id}/computations', headers=headers(token), json={'selected_regime': 'NEW'}).json()
        client.post(f"/api/computations/{comp['id']}/review", headers=headers(token), json={'decision': 'APPROVE', 'justification': 'Reviewed and approved for export validation test.'})
        payload = {
            'computation_run_id': comp['id'], 'form_code': 'ITR_1', 'intermediary_city': 'Mumbai', 'schema_version': 'V1.1',
            'identity': {'pan': 'ABCDE1234F', 'first_name': 'Test', 'middle_name': '', 'surname': 'Taxpayer', 'date_of_birth': '1990-01-01', 'email': 'taxpayer@example.com', 'mobile': '9999999999', 'address': {'ResidenceNo': '1', 'ResidenceName': 'Test'}, 'verification_place': 'Mumbai', 'verification_capacity': 'S'}
        }
        r = client.post(f'/api/cases/{case_id}/exports', headers=headers(token), json=payload)
        assert r.status_code == 503
        assert 'schema is not pinned' in r.text


def test_cross_tenant_case_access_is_denied():
    with TestClient(app) as client:
        token = bootstrap(client)
        case_id = create_case(client, token)
        with SessionLocal() as db:
            tenant2 = Tenant(name='Other Firm', slug='other-firm')
            user2 = User(email='other@example.com', full_name='Other Owner', password_hash=hash_password('AnotherSecurePass123!'))
            db.add_all([tenant2, user2]); db.flush()
            db.add(Membership(tenant_id=tenant2.id, user_id=user2.id, role='firm_owner', status='ACTIVE')); db.commit()
            actor2 = Actor(user2.id, tenant2.id, 'firm_owner', False, frozenset({'*'}))
            try:
                assert_case_access(db, actor2, case_id)
                denied = False
            except HTTPException as exc:
                denied = exc.status_code == 404
            assert denied


def test_provisional_computation_persists_review_items():
    with TestClient(app) as client:
        token = bootstrap(client)
        case_id = create_case(client, token)
        accept_fact(client, token, case_id, 'SALARY.EMPLOYMENT', {
            'employment_id': 'EMP1', 'employer_name': 'Example Pvt Ltd',
            'components': [{'code': 'GROSS', 'label': 'Gross salary', 'amount': '2100000', 'exempt_under_section_10': '0', 'evidence_fact_ids': []}],
            'professional_tax': '0', 'employer_tds': '0', 'is_pension': False, 'is_family_pension': False, 'evidence_fact_ids': []
        }, entity_key='EMP1', key='salary-interest-context')
        result = client.post(f'/api/cases/{case_id}/computations', headers=headers(token), json={'selected_regime': 'NEW'})
        assert result.status_code == 201
        assert result.json()['status'] == 'PROVISIONAL'
        items = client.get(f'/api/cases/{case_id}/missing-items', headers=headers(token))
        assert items.status_code == 200
        codes = {item['code'] for item in items.json() if item['status'] == 'OPEN'}
        assert 'AUTO_INTEREST_234B_CONTEXT_MISSING' in codes
        assert 'AUTO_INTEREST_234C_CONTEXT_MISSING' in codes


def test_conflicting_candidates_create_reconciliation_item():
    with TestClient(app) as client:
        token = bootstrap(client)
        case_id = create_case(client, token)
        first = client.post(f'/api/cases/{case_id}/candidate-facts', headers=headers(token), json={
            'field_code': 'OTHER_INCOME.BANK_INTEREST.TOTAL', 'entity_key': 'BANK1', 'value_type': 'money',
            'value': {'amount': '18500', 'currency': 'INR'}, 'evidence_claim_ids': [], 'idempotency_key': 'bank-source-a'
        }).json()
        client.post(f"/api/candidate-facts/{first['id']}/review", headers=headers(token), json={'decision': 'ACCEPT', 'justification': 'Accepted from bank interest certificate after review.'})
        second = client.post(f'/api/cases/{case_id}/candidate-facts', headers=headers(token), json={
            'field_code': 'OTHER_INCOME.BANK_INTEREST.TOTAL', 'entity_key': 'BANK1', 'value_type': 'money',
            'value': {'amount': '17900', 'currency': 'INR'}, 'evidence_claim_ids': [], 'idempotency_key': 'bank-source-b'
        }).json()
        client.post(f"/api/candidate-facts/{second['id']}/review", headers=headers(token), json={'decision': 'ACCEPT', 'justification': 'Accepted AIS candidate temporarily to trigger reconciliation.'})
        result = client.get(f'/api/cases/{case_id}/reconciliation', headers=headers(token))
        assert result.status_code == 200
        assert any(item['category'] == 'OTHER_INCOME.BANK_INTEREST.TOTAL' and item['status'] == 'DIFFERENCE' and item['difference_amount'] == '600.00' for item in result.json())


def test_audit_events_are_exposed_only_with_case_access():
    with TestClient(app) as client:
        token = bootstrap(client)
        case_id = create_case(client, token)
        result = client.get(f'/api/cases/{case_id}/audit-events', headers=headers(token))
        assert result.status_code == 200
        assert any(item['action'] == 'case.created' for item in result.json())


def test_unregistered_ai_tool_is_denied():
    with TestClient(app) as client:
        token = bootstrap(client)
        case_id = create_case(client, token)
        result = client.post(
            f'/api/cases/{case_id}/assistant/tools',
            headers=headers(token),
            json={'name': 'approve_fact', 'arguments': {}, 'idempotency_key': 'blocked-tool-1'},
        )
        assert result.status_code in {400, 403, 422}
        assert 'literal_error' in result.text.lower() or 'tool' in result.text.lower() or 'capability' in result.text.lower()


def test_locked_case_rejects_new_candidate_fact():
    with TestClient(app) as client:
        token = bootstrap(client)
        case_id = create_case(client, token)
        accept_fact(client, token, case_id, 'SALARY.EMPLOYMENT', {
            'employment_id': 'EMP1', 'employer_name': 'Example Pvt Ltd',
            'components': [{'code': 'GROSS', 'label': 'Gross salary', 'amount': '500000', 'exempt_under_section_10': '0', 'evidence_fact_ids': []}],
            'professional_tax': '0', 'employer_tds': '0', 'is_pension': False,
            'is_family_pension': False, 'evidence_fact_ids': []
        }, entity_key='EMP1', key='salary-lock')
        comp = client.post(f'/api/cases/{case_id}/computations', headers=headers(token), json={'selected_regime': 'NEW'}).json()
        review = client.post(
            f"/api/computations/{comp['id']}/review",
            headers=headers(token),
            json={'decision': 'APPROVE', 'justification': 'Approved before immutable case lock test.'},
        )
        assert review.status_code == 200
        lock = client.post(f'/api/cases/{case_id}/lock', headers=headers(token))
        assert lock.status_code == 200
        mutation = client.post(f'/api/cases/{case_id}/candidate-facts', headers=headers(token), json={
            'field_code': 'OTHER_INCOME.BANK_INTEREST.TOTAL', 'entity_key': 'ROOT', 'value_type': 'money',
            'value': {'amount': '1', 'currency': 'INR'}, 'evidence_claim_ids': [], 'idempotency_key': 'after-lock'
        })
        assert mutation.status_code == 409
        assert 'locked' in mutation.text.lower()


def test_password_protected_pdf_is_rejected_before_storage():
    import fitz
    from app.document_security import inspect_document

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), 'Confidential tax document')
    protected = document.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw='owner-password',
        user_pw='user-password',
    )
    document.close()
    with pytest.raises(HTTPException) as exc:
        inspect_document('protected.pdf', 'application/pdf', protected)
    assert exc.value.status_code == 422
    assert 'password-protected' in str(exc.value.detail).lower()


def test_http_only_cookie_session_and_refresh_work_without_browser_storage():
    with TestClient(app) as client:
        bootstrap(client)
        assert client.cookies.get('gp_access')
        assert client.cookies.get('gp_refresh')
        me = client.get('/api/auth/me')
        assert me.status_code == 200
        refreshed = client.post('/api/auth/refresh', json={})
        assert refreshed.status_code == 200, refreshed.text
        assert client.cookies.get('gp_access')
