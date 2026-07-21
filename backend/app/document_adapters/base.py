from __future__ import annotations

import csv
import io
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import fitz


@dataclass(frozen=True)
class SourceLocation:
    page_index: int | None = None
    bounding_box: list[float] | None = None
    original_text: str | None = None


@dataclass(frozen=True)
class ExtractedClaim:
    field_code: str
    value_type: str
    value: dict[str, Any]
    source: SourceLocation
    confidence: Decimal
    validations: list[dict[str, Any]] = field(default_factory=list)
    entity_key: str = "ROOT"


@dataclass
class AdapterResult:
    adapter_code: str
    adapter_version: str
    document_type: str
    claims: list[ExtractedClaim] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentAdapter(ABC):
    code: str
    version: str = "1.0.0"
    document_type: str

    @abstractmethod
    def supports(self, filename: str, mime_type: str, content: bytes) -> Decimal:
        raise NotImplementedError

    @abstractmethod
    def extract(self, filename: str, mime_type: str, content: bytes) -> AdapterResult:
        raise NotImplementedError


def parse_decimal(raw: object) -> Decimal | None:
    if raw is None:
        return None
    text = str(raw).strip().replace("₹", "").replace(",", "")
    text = re.sub(r"[^0-9.()\-]", "", text)
    if not text:
        return None
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def money_value(value: Decimal, currency: str = "INR") -> dict[str, str]:
    return {"amount": format(value.quantize(Decimal("0.01")), "f"), "currency": currency}


def pdf_pages(content: bytes) -> list[dict[str, Any]]:
    doc = fitz.open(stream=content, filetype="pdf")
    pages: list[dict[str, Any]] = []
    for index, page in enumerate(doc):
        blocks = page.get_text("blocks")
        text = page.get_text("text")
        pages.append({
            "page_index": index,
            "text": text,
            "blocks": [
                {"bbox": [float(x0), float(y0), float(x1), float(y1)], "text": block_text}
                for x0, y0, x1, y1, block_text, *_ in blocks
            ],
        })
    return pages


def find_amount_claim(pages: list[dict[str, Any]], patterns: list[str], field_code: str, confidence: str = "0.90", entity_key: str = "ROOT") -> ExtractedClaim | None:
    compiled = [re.compile(pattern, re.IGNORECASE | re.MULTILINE) for pattern in patterns]
    for page in pages:
        for block in page["blocks"]:
            for regex in compiled:
                match = regex.search(block["text"])
                if not match:
                    continue
                amount = parse_decimal(match.group(match.lastindex or 1))
                if amount is None:
                    continue
                return ExtractedClaim(
                    field_code=field_code,
                    value_type="money",
                    value=money_value(amount),
                    source=SourceLocation(page["page_index"], block["bbox"], match.group(0)),
                    confidence=Decimal(confidence),
                    entity_key=entity_key,
                )
    return None


def load_json(content: bytes) -> Any:
    return json.loads(content.decode("utf-8-sig"))


def load_csv(content: bytes) -> list[dict[str, str]]:
    text = content.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    return list(csv.DictReader(io.StringIO(text), dialect=dialect))
