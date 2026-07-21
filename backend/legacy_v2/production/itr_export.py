from __future__ import annotations

from datetime import datetime, timezone

from .hashing import sha256_json


class ExportBlockedError(ValueError):
    pass


def build_internal_audit_export(*, filing: dict, snapshot: dict, computation: dict, form_eligibility: dict) -> dict:
    """Builds a Green Papaya audit package, not an ITD upload file.

    The previous code claimed to generate schema-compliant ITR JSON without using the
    official schema. This function is deliberately labelled and cannot be confused
    with an Income Tax Department upload artefact.
    """
    package = {
        "export_type": "GREEN_PAPAYA_INTERNAL_AUDIT_PACKAGE",
        "not_for_itd_upload": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case": {
            "id": filing["id"],
            "assessment_year": filing.get("assessment_year"),
            "selected_regime": filing.get("selected_regime"),
        },
        "fact_snapshot": snapshot,
        "computation": computation,
        "form_eligibility": form_eligibility,
    }
    package["package_hash"] = sha256_json(package)
    return package


def validate_ready_for_official_export(*, filing: dict, computation: dict, form_eligibility: dict, pending_count: int) -> None:
    failures = []
    if computation.get("computation_status") != "COMPLETE":
        failures.append("Computation is not COMPLETE")
    if pending_count:
        failures.append(f"{pending_count} candidate facts remain unresolved")
    if form_eligibility.get("status") != "APPROVED":
        failures.append("Form eligibility has not been approved by a CA reviewer")
    if not filing.get("final_review_approval_id"):
        failures.append("Final CA review approval is missing")
    if failures:
        raise ExportBlockedError("; ".join(failures))


def build_official_itr_export(*args, **kwargs):
    raise ExportBlockedError(
        "Official ITR JSON export is intentionally disabled until the form-specific "
        "AY 2026-27 schema mapper and official validation suite are installed and approved."
    )
