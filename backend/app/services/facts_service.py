from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..audit import append_audit
from ..db_models import CandidateFact, CanonicalFact, EvidenceClaim, FactSnapshot, ReconciliationItem, TaxCase
from ..security import Actor, assert_case_access, assert_case_mutable, stable_json_hash
from ..tax_engine.models import (
    BusinessActivity,
    CapitalGainTransaction,
    DeductionClaims,
    EmploymentIncome,
    FilingContext,
    ForeignAsset,
    ForeignIncomeItem,
    HouseProperty,
    OtherIncome,
    Regime,
    SalaryComponent,
    TaxFactSnapshot,
    TaxPayment,
    TaxpayerProfile,
    VDATransaction,
)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return json.loads(json.dumps(value, default=str))


def propose_candidate(
    db: Session,
    *,
    actor: Actor,
    case_id: str,
    field_code: str,
    entity_key: str,
    value_type: str,
    value: dict,
    evidence_claim_ids: list[str],
    idempotency_key: str,
    source: str = "MANUAL",
    explanation: str | None = None,
) -> CandidateFact:
    case = assert_case_access(db, actor, case_id, "fact:propose")
    assert_case_mutable(case)
    existing = db.scalar(select(CandidateFact).where(CandidateFact.tenant_id == actor.tenant_id, CandidateFact.idempotency_key == idempotency_key))
    if existing:
        return existing
    if evidence_claim_ids:
        count = db.scalar(
            select(func.count()).select_from(EvidenceClaim).where(
                EvidenceClaim.tenant_id == actor.tenant_id,
                EvidenceClaim.case_id == case_id,
                EvidenceClaim.id.in_(evidence_claim_ids),
            )
        )
        if count != len(set(evidence_claim_ids)):
            raise HTTPException(status_code=400, detail="One or more evidence claims are invalid for this case")
    candidate = CandidateFact(
        tenant_id=actor.tenant_id,
        case_id=case_id,
        field_code=field_code,
        value_type=value_type,
        value_json={**value, "entity_key": entity_key},
        tax_period=case.tax_period,
        evidence_claim_ids=evidence_claim_ids,
        source=source,
        idempotency_key=idempotency_key,
        proposed_by=actor.user_id,
        model_explanation=explanation,
        status="PENDING_REVIEW",
    )
    db.add(candidate)
    db.flush()
    append_audit(db, actor=actor, action="candidate_fact.proposed", entity_type="candidate_fact", entity_id=candidate.id, case_id=case_id, after=candidate.value_json, metadata={"field_code": field_code, "source": source})
    return candidate


def review_candidate(
    db: Session,
    *,
    actor: Actor,
    candidate_id: str,
    decision: str,
    justification: str,
    corrected_value: dict | None = None,
    entity_key: str | None = None,
) -> tuple[CandidateFact, CanonicalFact | None]:
    candidate = db.scalar(select(CandidateFact).where(CandidateFact.id == candidate_id, CandidateFact.tenant_id == actor.tenant_id))
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate fact not found")
    case = assert_case_access(db, actor, candidate.case_id, "review:*")
    assert_case_mutable(case)
    if candidate.status not in {"PENDING_REVIEW", "CONFLICTING", "VALIDATED", "EXTRACTED"}:
        raise HTTPException(status_code=409, detail="Candidate has already been reviewed")
    candidate.reviewed_by = actor.user_id
    candidate.reviewed_at = datetime.now(timezone.utc)
    candidate.review_justification = justification
    canonical = None
    if decision == "REJECT":
        candidate.status = "REJECTED"
    elif decision == "CONFLICT":
        candidate.status = "CONFLICTING"
    elif decision == "ACCEPT":
        candidate.status = "ACCEPTED"
        value = corrected_value if corrected_value is not None else dict(candidate.value_json)
        key = entity_key or value.pop("entity_key", None) or candidate.value_json.get("entity_key") or "ROOT"
        current = db.scalar(
            select(CanonicalFact).where(
                CanonicalFact.case_id == candidate.case_id,
                CanonicalFact.field_code == candidate.field_code,
                CanonicalFact.entity_key == key,
                CanonicalFact.is_current.is_(True),
            )
        )
        next_version = 1
        if current:
            current.is_current = False
            next_version = current.version + 1
        canonical = CanonicalFact(
            tenant_id=actor.tenant_id,
            case_id=candidate.case_id,
            field_code=candidate.field_code,
            entity_key=key,
            value_type=candidate.value_type,
            value_json=value,
            tax_period=candidate.tax_period,
            evidence_claim_ids=candidate.evidence_claim_ids,
            source_candidate_id=candidate.id,
            version=next_version,
            is_current=True,
            approved_by=actor.user_id,
        )
        db.add(canonical)
        db.flush()
        if current:
            current.superseded_by_id = canonical.id
        _sync_reconciliation_for_fact(db, actor=actor, candidate=candidate, canonical=canonical, entity_key=key)
    else:
        raise HTTPException(status_code=400, detail="Unsupported review decision")
    db.flush()
    append_audit(db, actor=actor, action=f"candidate_fact.{decision.lower()}", entity_type="candidate_fact", entity_id=candidate.id, case_id=candidate.case_id, before={"status": "PENDING_REVIEW"}, after={"status": candidate.status, "canonical_fact_id": canonical.id if canonical else None}, metadata={"justification": justification})
    return candidate, canonical




def _sync_reconciliation_for_fact(db: Session, *, actor: Actor, candidate: CandidateFact, canonical: CanonicalFact, entity_key: str) -> None:
    candidates = list(db.scalars(select(CandidateFact).where(
        CandidateFact.tenant_id == actor.tenant_id,
        CandidateFact.case_id == candidate.case_id,
        CandidateFact.field_code == candidate.field_code,
    )))
    relevant = [row for row in candidates if (row.value_json.get("entity_key") or "ROOT") == entity_key]
    if len(relevant) < 2:
        return
    source_values = {f"{row.source}:{row.id}": row.value_json for row in relevant}
    fingerprints = {stable_json_hash({k: v for k, v in row.value_json.items() if k != "entity_key"}) for row in relevant}
    status = "MATCHED" if len(fingerprints) == 1 else "DIFFERENCE"
    amounts = []
    for row in relevant:
        raw = row.value_json.get("amount")
        if raw is not None:
            try:
                amounts.append(Decimal(str(raw)))
            except Exception:
                pass
    difference = max(amounts) - min(amounts) if len(amounts) >= 2 else None
    item = db.scalar(select(ReconciliationItem).where(
        ReconciliationItem.tenant_id == actor.tenant_id,
        ReconciliationItem.case_id == candidate.case_id,
        ReconciliationItem.category == candidate.field_code,
        ReconciliationItem.entity_key == entity_key,
        ReconciliationItem.resolved_at.is_(None),
    ))
    if not item:
        item = ReconciliationItem(tenant_id=actor.tenant_id, case_id=candidate.case_id, category=candidate.field_code, entity_key=entity_key, source_values=source_values, accepted_fact_id=canonical.id, status=status, difference_amount=difference)
        db.add(item)
    else:
        item.source_values = source_values; item.accepted_fact_id = canonical.id; item.status = status; item.difference_amount = difference


def list_current_facts(db: Session, actor: Actor, case_id: str) -> list[CanonicalFact]:
    assert_case_access(db, actor, case_id, "fact:read")
    return list(db.scalars(select(CanonicalFact).where(CanonicalFact.tenant_id == actor.tenant_id, CanonicalFact.case_id == case_id, CanonicalFact.is_current.is_(True)).order_by(CanonicalFact.field_code, CanonicalFact.entity_key)))


def _amount(value: dict, default: str = "0") -> Decimal:
    raw = value.get("amount", value.get("value", default))
    return Decimal(str(raw or default))


def _group_facts(rows: list[CanonicalFact]) -> dict[str, list[CanonicalFact]]:
    grouped: dict[str, list[CanonicalFact]] = {}
    for row in rows:
        grouped.setdefault(row.field_code, []).append(row)
    return grouped


def build_tax_snapshot(db: Session, *, actor: Actor, case_id: str, selected_regime: str | None = None) -> tuple[FactSnapshot, TaxFactSnapshot]:
    case = assert_case_access(db, actor, case_id, "computation:run")
    assert_case_mutable(case)
    rows = list_current_facts(db, actor, case_id)
    grouped = _group_facts(rows)
    ids = [row.id for row in rows]

    profile_data = (grouped.get("TAXPAYER.PROFILE") or [None])[0]
    profile = TaxpayerProfile(**(profile_data.value_json if profile_data else {}))

    employments: list[EmploymentIncome] = []
    for row in grouped.get("SALARY.EMPLOYMENT", []):
        employments.append(EmploymentIncome(**row.value_json))
    granular_salary = {row.entity_key for code in ["SALARY.GROSS", "SALARY.EMPLOYER.NAME", "SALARY.EMPLOYER.TAN", "SALARY.PROFESSIONAL_TAX", "SALARY.SECTION10_EXEMPTIONS", "TAX_PAYMENT.TDS.SALARY"] for row in grouped.get(code, [])}
    payments: list[TaxPayment] = []
    for key in sorted(granular_salary):
        def one(code):
            return next((r for r in grouped.get(code, []) if r.entity_key == key), None)
        gross = one("SALARY.GROSS")
        if not gross:
            continue
        exemption = one("SALARY.SECTION10_EXEMPTIONS")
        prof = one("SALARY.PROFESSIONAL_TAX")
        employer = one("SALARY.EMPLOYER.NAME")
        tan = one("SALARY.EMPLOYER.TAN")
        tds = one("TAX_PAYMENT.TDS.SALARY")
        evidence = sorted(set(sum([r.evidence_claim_ids for r in [gross, exemption, prof, employer, tan, tds] if r], [])))
        employments.append(EmploymentIncome(
            employment_id=key,
            employer_name=(employer.value_json.get("text") if employer else key),
            employer_tan=(tan.value_json.get("text") if tan else None),
            components=[SalaryComponent(code="GROSS", label="Gross salary", amount=_amount(gross.value_json), exempt_under_section_10=_amount(exemption.value_json) if exemption else Decimal("0"), evidence_fact_ids=[gross.id])],
            professional_tax=_amount(prof.value_json) if prof else Decimal("0"),
            employer_tds=_amount(tds.value_json) if tds else Decimal("0"),
            evidence_fact_ids=evidence,
        ))
        if tds:
            payments.append(TaxPayment(payment_id=f"salary-tds-{key}", payment_type="TDS", amount=_amount(tds.value_json), deductor_tan=(tan.value_json.get("text") if tan else None), evidence_fact_ids=[tds.id]))

    house_properties = [HouseProperty(**row.value_json) for row in grouped.get("HOUSE_PROPERTY", [])]
    capital_transactions = [CapitalGainTransaction(**row.value_json) for row in grouped.get("CAPITAL_GAIN.TRANSACTION", [])]
    business_activities = [BusinessActivity(**row.value_json) for row in grouped.get("BUSINESS.ACTIVITY", [])]
    vda_transactions = [VDATransaction(**row.value_json) for row in grouped.get("VDA.TRANSACTION", [])]
    foreign_income = [ForeignIncomeItem(**row.value_json) for row in grouped.get("FOREIGN_INCOME.ITEM", [])]
    foreign_assets = [ForeignAsset(**row.value_json) for row in grouped.get("FOREIGN_ASSET", [])]
    payments.extend(TaxPayment(**row.value_json) for row in grouped.get("TAX_PAYMENT", []))

    other = OtherIncome(**((grouped.get("OTHER_INCOME") or [None])[0].value_json if grouped.get("OTHER_INCOME") else {}))
    bank_total = sum((_amount(r.value_json) for r in grouped.get("OTHER_INCOME.BANK_INTEREST.TOTAL", [])), Decimal("0"))
    if bank_total:
        other.deposit_interest += bank_total
    deductions = DeductionClaims(**((grouped.get("DEDUCTIONS") or [None])[0].value_json if grouped.get("DEDUCTIONS") else {}))
    filing = FilingContext(**((grouped.get("FILING.CONTEXT") or [None])[0].value_json if grouped.get("FILING.CONTEXT") else {}))

    snapshot_data = TaxFactSnapshot(
        snapshot_id="pending",
        case_id=case.id,
        assessment_year=case.assessment_year,
        financial_year=case.tax_period,
        act_namespace=case.act_namespace,
        selected_regime=Regime(selected_regime or case.selected_regime),
        profile=profile,
        employments=employments,
        house_properties=house_properties,
        capital_transactions=capital_transactions,
        business_activities=business_activities,
        vda_transactions=vda_transactions,
        other_income=other,
        deductions=deductions,
        tax_payments=payments,
        foreign_income=foreign_income,
        foreign_assets=foreign_assets,
        filing=filing,
        approved_fact_ids=ids,
    )
    body = snapshot_data.model_dump(mode="json", exclude={"snapshot_hash", "snapshot_id"})
    digest = stable_json_hash(body)
    existing = db.scalar(select(FactSnapshot).where(FactSnapshot.snapshot_hash == digest))
    if existing:
        snapshot_data.snapshot_id = existing.id
        snapshot_data.snapshot_hash = existing.snapshot_hash
        return existing, snapshot_data
    record = FactSnapshot(tenant_id=actor.tenant_id, case_id=case.id, facts_json=body, snapshot_hash=digest, created_by=actor.user_id, immutable=True)
    db.add(record)
    db.flush()
    snapshot_data.snapshot_id = record.id
    snapshot_data.snapshot_hash = digest
    record.facts_json = snapshot_data.model_dump(mode="json")
    append_audit(db, actor=actor, action="fact_snapshot.created", entity_type="fact_snapshot", entity_id=record.id, case_id=case.id, after={"snapshot_hash": digest, "fact_count": len(ids)})
    return record, snapshot_data


def load_tax_snapshot(record: FactSnapshot) -> TaxFactSnapshot:
    return TaxFactSnapshot(**record.facts_json)
