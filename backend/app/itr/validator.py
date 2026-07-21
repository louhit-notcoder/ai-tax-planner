from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from .schema_registry import OfficialSchemaRegistry


@dataclass(frozen=True)
class ValidationErrorItem:
    code: str
    path: str
    message: str
    category: str = "SCHEMA"


class OfficialITRValidator:
    def __init__(self, registry: OfficialSchemaRegistry | None = None):
        self.registry = registry or OfficialSchemaRegistry()

    def validate(self, form_code: str, payload: dict[str, Any]) -> list[ValidationErrorItem]:
        schema = self.registry.load_schema(form_code)
        validator_class = validator_for(schema)
        validator_class.check_schema(schema)
        validator = validator_class(schema, format_checker=FormatChecker())
        errors = [
            ValidationErrorItem(
                code="OFFICIAL_SCHEMA_ERROR",
                path="$." + ".".join(str(item) for item in error.absolute_path),
                message=error.message,
            )
            for error in sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
        ]
        errors.extend(self._product_validations(form_code, payload))
        return errors

    def _product_validations(self, form_code: str, payload: dict[str, Any]) -> list[ValidationErrorItem]:
        errors: list[ValidationErrorItem] = []
        if "ITR" not in payload or form_code.replace("_", "") not in payload.get("ITR", {}):
            errors.append(ValidationErrorItem("ROOT_FORM_MISMATCH", "$.ITR", f"Payload does not contain {form_code} root", "PRODUCT"))
        return errors
