"""LLM-assisted document adapters.

These subclass the same `DocumentAdapter` contract as the regex adapters and
return the same `ExtractedClaim`s, so extraction quality improves without any
change to the candidate-fact → human review → canonical-fact pipeline. When the
vision model is not configured, `supports()` returns 0 and the deterministic
regex adapters take over, so nothing regresses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .base import AdapterResult, DocumentAdapter, ExtractedClaim, SourceLocation, money_value, parse_decimal, pdf_pages
from .vision import VisionExtractionClient, OpenRouterVisionClient, render_document_images

MAX_CONFIDENCE = Decimal("0.99")


@dataclass(frozen=True)
class FieldSpec:
    field_code: str
    value_type: str  # "money" | "text"
    description: str


class LLMDocumentAdapter(DocumentAdapter):
    fields: list[FieldSpec] = []
    instruction: str = ""

    def __init__(self, client: VisionExtractionClient | None = None) -> None:
        self.client = client or OpenRouterVisionClient()

    # --- classification -----------------------------------------------------
    def _detect(self, filename: str, mime_type: str, content: bytes) -> Decimal:
        """Subclass returns a 0..1 score for 'is this that document type'."""
        raise NotImplementedError

    def supports(self, filename: str, mime_type: str, content: bytes) -> Decimal:
        if not self.client.enabled():
            return Decimal("0")
        return self._detect(filename, mime_type, content)

    # --- extraction ---------------------------------------------------------
    def _schema_hint(self) -> str:
        lines = [f"- {spec.field_code} ({spec.value_type}): {spec.description}" for spec in self.fields]
        return (
            "Extract ONLY these fields from the attached document pages. Do not compute or infer totals.\n"
            + "\n".join(lines)
            + "\n\nReturn strict JSON: {\"fields\": [{\"field_code\": <one code above>, "
            "\"value\": <string; for money the plain number in rupees, no symbols/commas>, "
            "\"confidence\": <0..1>, \"page_index\": <0-based page the value came from>, "
            "\"quote\": <the exact text you read the value from>}]}. "
            "Omit any field you cannot find. Never guess a number."
        )

    def extract(self, filename: str, mime_type: str, content: bytes) -> AdapterResult:
        images = render_document_images(content, mime_type)
        warnings: list[str] = []
        try:
            rows = self.client.extract(images, self.instruction, self._schema_hint())
        except Exception as exc:  # never crash extraction on a model/network error
            return AdapterResult(self.code, self.version, self.document_type, [], [f"Vision extraction failed: {exc}"], {"page_count": len(images), "extraction": "llm", "failed": True})
        claims = self.claims_from_rows(rows, page_count=len(images))
        claims = self.postprocess(claims, warnings)
        return AdapterResult(self.code, self.version, self.document_type, claims, warnings, {"page_count": len(images), "extraction": "llm", "raw_field_count": len(rows)})

    def claims_from_rows(self, rows: list[dict[str, Any]], *, page_count: int) -> list[ExtractedClaim]:
        """Pure mapping from model output rows to evidence-linked claims.

        Kept free of I/O so it is directly unit-testable. Unknown fields, bad
        numbers, and out-of-range confidences are dropped/clamped rather than
        trusted.
        """
        spec_by_code = {spec.field_code: spec for spec in self.fields}
        claims: list[ExtractedClaim] = []
        for row in rows:
            code = str(row.get("field_code", "")).strip()
            spec = spec_by_code.get(code)
            if spec is None:
                continue
            raw_value = row.get("value")
            if raw_value is None or str(raw_value).strip() == "":
                continue
            if spec.value_type == "money":
                amount = parse_decimal(raw_value)
                if amount is None:
                    continue
                value: dict[str, Any] = money_value(amount)
                validations = [{"rule": "non_negative", "status": "PASS" if amount >= 0 else "REVIEW"}]
            else:
                value = {"text": str(raw_value).strip()}
                validations = []
            confidence = self._clamp_confidence(row.get("confidence"))
            page_index = self._page_index(row.get("page_index"), page_count)
            quote = row.get("quote")
            claims.append(ExtractedClaim(
                field_code=code,
                value_type=spec.value_type,
                value=value,
                source=SourceLocation(page_index=page_index, bounding_box=None, original_text=str(quote) if quote else None),
                confidence=confidence,
                validations=validations,
            ))
        return claims

    def postprocess(self, claims: list[ExtractedClaim], warnings: list[str]) -> list[ExtractedClaim]:
        return claims

    @staticmethod
    def _clamp_confidence(raw: Any) -> Decimal:
        try:
            value = Decimal(str(raw))
        except Exception:
            return Decimal("0.50")
        if value < 0:
            return Decimal("0")
        return min(value, MAX_CONFIDENCE)

    @staticmethod
    def _page_index(raw: Any, page_count: int) -> int | None:
        try:
            index = int(raw)
        except (TypeError, ValueError):
            return None
        if 0 <= index < max(page_count, 1):
            return index
        return None


class Form16LLMAdapter(LLMDocumentAdapter):
    code = "FORM16_LLM"
    version = "3.0.0"
    document_type = "FORM_16"

    instruction = (
        "You are a meticulous Indian tax document reader assisting a Chartered Accountant. "
        "You read TDS certificates (Form 16 Part A and Part B) and report exactly what is printed. "
        "You never calculate, estimate, or fill in missing values."
    )

    fields = [
        FieldSpec("SALARY.EMPLOYER.NAME", "text", "Name of the employer / deductor."),
        FieldSpec("SALARY.EMPLOYER.TAN", "text", "TAN of the deductor (format AAAA99999A)."),
        FieldSpec("SALARY.GROSS", "money", "Gross salary (section 17(1)+17(2)+17(3) total gross, before exemptions/deductions)."),
        FieldSpec("SALARY.SECTION10_EXEMPTIONS", "money", "Total exemptions claimed under section 10 (HRA, LTA, etc.)."),
        FieldSpec("SALARY.PROFESSIONAL_TAX", "money", "Tax on employment / professional tax under section 16(iii)."),
        FieldSpec("TAX_PAYMENT.TDS.SALARY", "money", "Total tax deducted at source (TDS) on this salary."),
    ]

    _TOKENS = ("form no. 16", "certificate under section 203", "part b", "tan of deductor", "form 16")

    def _detect(self, filename: str, mime_type: str, content: bytes) -> Decimal:
        mime = (mime_type or "").lower()
        name = (filename or "").lower()
        # Text PDFs: detect Form 16 tokens directly.
        if "pdf" in mime or name.endswith(".pdf"):
            try:
                text = "\n".join(page["text"] for page in pdf_pages(content)[:3]).lower()
            except Exception:
                text = ""
            hits = sum(1 for token in self._TOKENS if token in text)
            if hits:
                # Beat the regex Form16Adapter (~0.92) when we clearly recognise it.
                return min(Decimal("0.90") + Decimal("0.03") * hits, Decimal("0.99"))
        # Scanned image or filename hint — regex can't read these at all, so the
        # vision path is the only one that can; claim it on a filename signal.
        if mime.startswith("image/") and re.search(r"form.?16", name):
            return Decimal("0.85")
        return Decimal("0")

    def postprocess(self, claims: list[ExtractedClaim], warnings: list[str]) -> list[ExtractedClaim]:
        tan = next((c.value.get("text") for c in claims if c.field_code == "SALARY.EMPLOYER.TAN"), None)
        employer = next((c.value.get("text") for c in claims if c.field_code == "SALARY.EMPLOYER.NAME"), None)
        entity = self._slug(tan or employer or "EMPLOYER_1")
        rebound = [self._with_entity(c, entity) for c in claims]

        gross = next((Decimal(c.value["amount"]) for c in rebound if c.field_code == "SALARY.GROSS"), None)
        exemptions = next((Decimal(c.value["amount"]) for c in rebound if c.field_code == "SALARY.SECTION10_EXEMPTIONS"), Decimal("0"))
        if gross is None:
            warnings.append("Gross salary was not identified; manual review is required.")
        elif exemptions > gross:
            warnings.append("Extracted section 10 exemptions exceed gross salary; verify before accepting.")
        return rebound

    @staticmethod
    def _with_entity(claim: ExtractedClaim, entity: str) -> ExtractedClaim:
        return ExtractedClaim(
            field_code=claim.field_code,
            value_type=claim.value_type,
            value=claim.value,
            source=claim.source,
            confidence=claim.confidence,
            validations=claim.validations,
            entity_key=entity,
        )

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^A-Z0-9]+", "_", (value or "").upper()).strip("_")[:80] or "EMPLOYER_1"
