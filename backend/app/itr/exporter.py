from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..config import get_settings
from ..tax_engine.models import ComputationResult, TaxFactSnapshot
from .schema_registry import OfficialSchemaRegistry
from .validator import OfficialITRValidator, ValidationErrorItem


class ITRIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pan: str
    first_name: str
    middle_name: str = ""
    surname: str
    date_of_birth: date
    email: str
    mobile: str
    address: dict[str, Any]
    aadhaar_last4: str | None = None
    verification_place: str
    verification_capacity: str = "S"


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    form_code: str
    identity: ITRIdentity
    computation: ComputationResult
    facts: TaxFactSnapshot
    intermediary_city: str
    schema_version: str = "V1.1"
    validation_version: str = "AY2026_27_PUBLISHED"
    creation_date: date
    ca_reviewer_approved: bool = False


@dataclass
class ExportBuildResult:
    status: str
    payload: dict[str, Any]
    validation_errors: list[ValidationErrorItem]
    schema_version: str
    schema_hash: str
    snapshot_hash: str


class SchemaDrivenITRExporter:
    """Builds ITR-1/ITR-2 payloads from the pinned official JSON schema.

    The schema creates the structural shell. Known schedules are mapped from the
    deterministic computation. A payload is never marked exportable until the
    pinned official schema and product gates both pass.
    """

    def __init__(self, registry: OfficialSchemaRegistry | None = None):
        self.registry = registry or OfficialSchemaRegistry()
        self.validator = OfficialITRValidator(self.registry)

    def build(self, request: ExportRequest) -> ExportBuildResult:
        if request.form_code not in {"ITR_1", "ITR_2"}:
            raise ValueError("Only ITR_1 and ITR_2 are supported")
        if request.form_code not in request.computation.form_eligibility.eligible_forms:
            raise ValueError("Requested return form is not eligible")
        if request.computation.status.value != "COMPLETE":
            raise ValueError("Only COMPLETE computations can be exported")
        if not request.ca_reviewer_approved:
            raise ValueError("CA reviewer approval is mandatory before official export")

        artifact = self.registry.get(request.form_code)
        schema = self.registry.load_schema(request.form_code)
        payload = self._required_shell(schema)
        root_name = request.form_code.replace("_", "")
        root = payload.setdefault("ITR", {}).setdefault(root_name, {})
        self._map_creation_info(root, request)
        self._map_form_info(root, root_name, request, schema)
        self._map_identity(root, request.identity)
        self._map_computation(root, request.computation)
        self._map_schedules(root, request.computation.schedule_data)
        self._map_verification(root, request.identity, request.creation_date)
        errors = self.validator.validate(request.form_code, payload)
        status = "READY_FOR_CA_REVIEW" if not errors else "VALIDATION_FAILED"
        snapshot_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        return ExportBuildResult(status, payload, errors, artifact.version, artifact.sha256, snapshot_hash)

    def _required_shell(self, schema: dict) -> dict:
        return self._build_node(schema, schema)

    def _build_node(self, node: dict, root_schema: dict, depth: int = 0):
        if depth > 80:
            return {}
        if "$ref" in node:
            ref = node["$ref"]
            if ref.startswith("#/definitions/"):
                return self._build_node(root_schema["definitions"][ref.split("/")[-1]], root_schema, depth + 1)
        if "default" in node:
            return copy.deepcopy(node["default"])
        if "enum" in node and node["enum"]:
            return copy.deepcopy(node["enum"][0])
        kind = node.get("type")
        if kind == "object" or "properties" in node:
            required = node.get("required", [])
            return {key: self._build_node(node["properties"][key], root_schema, depth + 1) for key in required if key in node.get("properties", {})}
        if kind == "array":
            min_items = node.get("minItems", 0)
            return [self._build_node(node.get("items", {}), root_schema, depth + 1) for _ in range(min_items)]
        if kind in {"integer", "number"}:
            return node.get("minimum", 0)
        if kind == "boolean":
            return False
        return ""

    def _map_creation_info(self, root, request):
        creation = root.setdefault("CreationInfo", {})
        settings = get_settings()
        creation.update({
            "SWVersionNo": settings.software_version[:10],
            "SWCreatedBy": settings.software_id,
            "JSONCreatedBy": settings.software_id,
            "JSONCreationDate": request.creation_date.isoformat(),
            "IntermediaryCity": request.intermediary_city,
            "Digest": "-",
        })

    def _map_form_info(self, root, root_name, request, schema):
        node = root.setdefault(f"Form_{root_name}", {})
        node.update({
            "FormName": root_name.replace("ITR", "ITR-"),
            "AssessmentYear": "2026",
            "SchemaVer": request.schema_version,
            "FormVer": request.schema_version,
        })

    def _map_identity(self, root, identity):
        targets = [root.setdefault("PersonalInfo", {}), root.setdefault("PartA_GEN1", {})]
        for target in targets:
            self._deep_set_by_key(target, "PAN", identity.pan)
            self._deep_set_by_key(target, "DOB", identity.date_of_birth.isoformat())
            self._deep_set_by_key(target, "DateOfBirth", identity.date_of_birth.isoformat())
            self._deep_set_by_key(target, "EmailAddress", identity.email)
            self._deep_set_by_key(target, "MobileNo", identity.mobile)
            self._deep_set_by_key(target, "FirstName", identity.first_name)
            self._deep_set_by_key(target, "MiddleName", identity.middle_name)
            self._deep_set_by_key(target, "SurNameOrOrgName", identity.surname)
            for key, value in identity.address.items():
                self._deep_set_by_key(target, key, value)

    def _map_computation(self, root, computation):
        result = computation.selected_result
        if not result:
            return
        mapping = {
            "GrossTotalIncome": result.gross_total_income,
            "TotalIncome": result.total_income,
            "TotalTaxPayable": result.total_tax_liability,
            "TotalTaxAndInterest": result.total_tax_liability,
            "TotalTaxesPaid": result.tax_paid,
            "BalTaxPayable": result.payable,
            "RefundDue": result.refund,
            "Rebate87A": result.rebate_87a,
            "Surcharge": result.surcharge,
            "EducationCess": result.cess,
            "InterestPayable": result.interest_234a + result.interest_234b + result.interest_234c,
            "FeePayable": result.fee_234f,
        }
        for key, value in mapping.items():
            self._deep_set_by_key(root, key, self._number(value))

    def _map_schedules(self, root, schedule_data):
        aliases = {
            "ScheduleS": "ScheduleS",
            "ScheduleHP": "ScheduleHP",
            "ScheduleOS": "ScheduleOS",
            "ScheduleVIA": "ScheduleVIA",
            "ScheduleIT": "ScheduleIT",
            "ScheduleTDS": "ScheduleTDS1",
            "ScheduleTCS": "ScheduleTCS",
            "ScheduleFA": "ScheduleFA",
            "ScheduleFSI": "ScheduleFSI",
            "ScheduleTR": "ScheduleTR1",
            "PartB_TI": "PartB-TI",
            "PartB_TTI": "PartB_TTI",
        }
        for source_key, target_key in aliases.items():
            if source_key in schedule_data and target_key in root:
                self._overlay_compatible(root[target_key], schedule_data[source_key])

    def _map_verification(self, root, identity, creation_date):
        verification = root.setdefault("Verification", {})
        for key, value in {
            "Declaration": {"AssesseeVerName": f"{identity.first_name} {identity.surname}".strip(), "FatherName": "", "AssesseeVerPAN": identity.pan},
            "Capacity": identity.verification_capacity,
            "Place": identity.verification_place,
            "Date": creation_date.isoformat(),
        }.items():
            if key in verification:
                self._overlay_compatible(verification[key], value) if isinstance(verification[key], (dict, list)) else verification.__setitem__(key, value)
            else:
                verification[key] = value

    def _overlay_compatible(self, target, source):
        if isinstance(target, dict) and isinstance(source, dict):
            for key, value in source.items():
                if key in target:
                    if isinstance(target[key], (dict, list)):
                        self._overlay_compatible(target[key], value)
                    else:
                        target[key] = self._number(value)
        elif isinstance(target, list) and isinstance(source, list):
            target.clear()
            target.extend(source)

    def _deep_set_by_key(self, obj, key, value):
        if isinstance(obj, dict):
            if key in obj:
                obj[key] = self._number(value)
            for nested in obj.values():
                self._deep_set_by_key(nested, key, value)
        elif isinstance(obj, list):
            for nested in obj:
                self._deep_set_by_key(nested, key, value)

    @staticmethod
    def _number(value):
        if isinstance(value, Decimal):
            integral = value.to_integral_value()
            return int(integral) if value == integral else float(value)
        return value
