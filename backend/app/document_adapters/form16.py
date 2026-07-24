from __future__ import annotations

import re
from decimal import Decimal

from .base import AdapterResult, DocumentAdapter, ExtractedClaim, SourceLocation, find_amount_claim, money_value, parse_decimal, pdf_pages


class Form16Adapter(DocumentAdapter):
    code = "FORM16_COMBINED"
    version = "3.0.0"
    document_type = "FORM_16"

    def supports(self, filename, mime_type, content):
        if "pdf" not in mime_type.lower() and not filename.lower().endswith(".pdf"):
            return Decimal("0")
        score = Decimal("0")
        name = filename.lower()
        if any(k in name for k in ["form16", "form-16", "form_16", "form 16", "f16"]):
            score += Decimal("0.40")
        try:
            text = "\n".join(page["text"] for page in pdf_pages(content)[:3]).lower()
        except Exception:
            return min(score, Decimal("0.99"))
        
        tokens = [
            r"\bform\s*[-._]?\s*(?:no\.?\s*)?16\b",
            r"\bcertificate\s+under\s+section\s+203\b",
            r"\bpart\s*[-._]?\s*[ab]\b",
            r"\btan\s+of\s+(?:the\s+)?deductor\b",
            r"\bpan\s+of\s+(?:the\s+)?deductor\b",
            r"\bpan\s+of\s+(?:the\s+)?employee\b",
            r"\bgross\s+salary\b",
            r"\btax\s+deducted\s+at\s+source\b",
            r"\bsection\s+17\(1\)\b",
        ]
        for token in tokens:
            if re.search(token, text):
                score += Decimal("0.20")
        return min(score, Decimal("0.99"))

    def extract(self, filename, mime_type, content):
        pages = pdf_pages(content)
        full_text = "\n".join(page["text"] for page in pages)
        employer = self._text_value(pages, [
            r"Name and address of the Employer\s*[:\-]?\s*([^\n]+)",
            r"Name of the Employer\s*[:\-]?\s*([^\n]+)",
            r"Name and address of Deductor\s*[:\-]?\s*([^\n]+)",
            r"Name of Deductor\s*[:\-]?\s*([^\n]+)",
        ])
        tan = self._text_value(pages, [
            r"TAN of the Deductor\s*[:\-]?\s*([A-Z]{4}\d{5}[A-Z])",
            r"TAN of Deductor\s*[:\-]?\s*([A-Z]{4}\d{5}[A-Z])",
            r"TAN\s*[:\-]?\s*([A-Z]{4}\d{5}[A-Z])",
        ])
        entity = tan or self._slug(employer or "EMPLOYER_1")
        claims: list[ExtractedClaim] = []
        for claim in [
            self._text_claim(pages, employer, "SALARY.EMPLOYER.NAME", entity, "0.96"),
            self._text_claim(pages, tan, "SALARY.EMPLOYER.TAN", entity, "0.98"),
            find_amount_claim(pages, [
                r"Gross Salary[^\d]*(\d[\d,]*(?:\.\d{1,2})?)",
                r"Total amount of salary received[^\d]*(\d[\d,]*(?:\.\d{1,2})?)",
                r"Salary as per provisions contained in section 17\(1\)[^\d]*(\d[\d,]*(?:\.\d{1,2})?)",
                r"Gross\s+Total[^\d]*(\d[\d,]*(?:\.\d{1,2})?)"
            ], "SALARY.GROSS", "0.94", entity),
            find_amount_claim(pages, [
                r"Standard deduction\s*(?:under\s*section\s*16\s*\(ia\)\s*)?[:\-]?\s*(\d[\d,]*(?:\.\d{1,2})?)",
                r"Standard deduction[^\d]*(\d[\d,]*(?:\.\d{1,2})?)"
            ], "SALARY.STANDARD_DEDUCTION", "0.95", entity),
            find_amount_claim(pages, [
                r"Total amount of exemption claimed under section 10[^\d]*(\d[\d,]*(?:\.\d{1,2})?)",
                r"Less\s*:\s*Allowances[^\d]*(\d[\d,]*(?:\.\d{1,2})?)",
                r"Exemption\s+under\s+section\s+10[^\d]*(\d[\d,]*(?:\.\d{1,2})?)"
            ], "SALARY.SECTION10_EXEMPTIONS", "0.92", entity),
            find_amount_claim(pages, [
                r"Tax on employment\s*[:\-]?\s*(\d[\d,]*(?:\.\d{1,2})?)",
                r"Professional tax\s*[:\-]?\s*(\d[\d,]*(?:\.\d{1,2})?)"
            ], "SALARY.PROFESSIONAL_TAX", "0.95", entity),
            find_amount_claim(pages, [
                r"Total tax deducted\s*[:\-]?\s*(\d[\d,]*(?:\.\d{1,2})?)",
                r"TDS on salary\s*[:\-]?\s*(\d[\d,]*(?:\.\d{1,2})?)",
                r"Tax deducted at source[^\d]*(\d[\d,]*(?:\.\d{1,2})?)"
            ], "TAX_PAYMENT.TDS.SALARY", "0.96", entity),
            find_amount_claim(pages, [
                r"(?:Section\s*)?80C[^\d]*(\d[\d,]*(?:\.\d{1,2})?)",
                r"Life Insurance Premiums[^\d]*(\d[\d,]*(?:\.\d{1,2})?)"
            ], "DEDUCTIONS.80C", "0.90", entity),
            find_amount_claim(pages, [
                r"(?:Section\s*)?80D[^\d]*(\d[\d,]*(?:\.\d{1,2})?)"
            ], "DEDUCTIONS.80D", "0.90", entity),
        ]:
            if claim:
                claims.append(claim)
        warnings = []
        if not any(c.field_code == "SALARY.GROSS" for c in claims):
            warnings.append("Gross salary was not identified; manual review required.")
        return AdapterResult(self.code, self.version, self.document_type, claims, warnings)

    @staticmethod
    def _slug(value):
        if not value:
            return "ROOT"
        return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")[:80]

    @staticmethod
    def _text_value(pages, patterns):
        for page in pages:
            for pattern in patterns:
                match = re.search(pattern, page["text"], re.IGNORECASE)
                if match:
                    return match.group(1).strip()
        return None

    @staticmethod
    def _text_claim(pages, value, field, entity, confidence):
        if not value:
            return None
        for page in pages:
            for block in page["blocks"]:
                if value.lower() in block["text"].lower():
                    return ExtractedClaim(field, "text", {"text": value}, SourceLocation(page["page_index"], block["bbox"], block["text"].strip()), Decimal(confidence), entity_key=entity)
        return ExtractedClaim(field, "text", {"text": value}, SourceLocation(), Decimal(confidence), entity_key=entity)
