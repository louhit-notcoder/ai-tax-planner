from __future__ import annotations

import re
from decimal import Decimal

from .base import AdapterResult, DocumentAdapter, ExtractedClaim, SourceLocation, load_csv, money_value, parse_decimal, pdf_pages


class TISAdapter(DocumentAdapter):
    code = "TIS_TABLE"
    version = "3.0.0"
    document_type = "TIS"

    def supports(self, filename, mime_type, content):
        name = filename.lower()
        if "tis" in name and (name.endswith(".csv") or name.endswith(".json")):
            return Decimal("0.95")
        return Decimal("0")

    def extract(self, filename, mime_type, content):
        rows = load_csv(content)
        claims = []
        for idx, row in enumerate(rows):
            description = str(row.get("Information Category") or row.get("Category") or row.get("Description") or "UNKNOWN")
            value = parse_decimal(row.get("Processed Value") or row.get("Derived Value") or row.get("Amount"))
            if value is None:
                continue
            claims.append(ExtractedClaim("RECONCILIATION.TIS.SUMMARY", "money", money_value(value), SourceLocation(original_text=str(row)), Decimal("0.97"), entity_key=f"{idx}:{description}"[:160]))
        return AdapterResult(self.code, self.version, self.document_type, claims, [] if claims else ["No TIS rows recognised."], {"row_count": len(rows)})


class Form26ASAdapter(DocumentAdapter):
    code = "FORM26AS_PDF"
    version = "3.0.0"
    document_type = "FORM_26AS"

    def supports(self, filename, mime_type, content):
        if not filename.lower().endswith(".pdf"):
            return Decimal("0")
        try:
            text = "\n".join(page["text"] for page in pdf_pages(content)[:2]).lower()
        except Exception:
            return Decimal("0")
        return Decimal("0.96") if "form 26as" in text or "tax credit statement" in text else Decimal("0")

    def extract(self, filename, mime_type, content):
        pages = pdf_pages(content)
        claims = []
        tan_pattern = re.compile(r"([A-Z]{4}\d{5}[A-Z])")
        amount_pattern = re.compile(r"(?:Tax Deducted|TDS|Total Tax Deducted)[^\d]*(\d[\d,]*(?:\.\d{1,2})?)", re.I)
        for page in pages:
            for block in page["blocks"]:
                tan = tan_pattern.search(block["text"])
                amount = amount_pattern.search(block["text"])
                if tan and amount:
                    value = parse_decimal(amount.group(1))
                    if value is not None:
                        claims.append(ExtractedClaim("RECONCILIATION.26AS.TDS", "money", money_value(value), SourceLocation(page["page_index"], block["bbox"], block["text"].strip()), Decimal("0.90"), entity_key=tan.group(1)))
        return AdapterResult(self.code, self.version, self.document_type, claims, [] if claims else ["26AS detected but no reliable TDS rows were extracted; manual review required."], {"page_count": len(pages)})
