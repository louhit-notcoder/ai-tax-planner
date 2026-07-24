from __future__ import annotations

import re
from decimal import Decimal

from .base import AdapterResult, DocumentAdapter, ExtractedClaim, SourceLocation, load_csv, money_value, parse_decimal, pdf_pages


class BankStatementAdapter(DocumentAdapter):
    code = "BANK_STATEMENT_GENERIC"
    version = "3.0.0"
    document_type = "BANK_STATEMENT"
    BANK_TOKENS = {
        "SBI": ["state bank of india", "sbi"],
        "HDFC": ["hdfc bank", "hdfc"],
        "ICICI": ["icici bank", "icici"],
        "KOTAK": ["kotak mahindra bank", "kotak"],
        "AXIS": ["axis bank", "axis"],
        "BOB": ["bank of baroda", "bob"],
        "PNB": ["punjab national bank", "pnb"],
        "CANARA": ["canara bank"],
        "YES": ["yes bank"],
        "INDUSIND": ["indusind bank"],
    }

    def supports(self, filename, mime_type, content):
        name = filename.lower()
        if (name.endswith(".csv") or name.endswith(".txt")) and any(token in name for token in ["bank", "statement", "sbi", "hdfc", "icici", "kotak", "axis", "passbook", "account"]):
            return Decimal("0.80")
        if name.endswith(".pdf") or "pdf" in (mime_type or "").lower():
            try:
                text = "\n".join(page["text"] for page in pdf_pages(content)[:3]).lower()
            except Exception:
                return Decimal("0")
            has_bank = any(token in text for values in self.BANK_TOKENS.values() for token in values) or any(t in name for t in ["bank", "statement", "passbook"])
            has_stmt = any(token in text for token in ["statement", "account number", "account no", "transaction date", "opening balance", "closing balance", "credit", "debit", "particulars", "narration"])
            if has_bank and has_stmt:
                return Decimal("0.85")
            elif has_stmt:
                return Decimal("0.60")
        return Decimal("0")

    def extract(self, filename, mime_type, content):
        if filename.lower().endswith(".csv"):
            return self._extract_csv(content)
        return self._extract_pdf(content)

    def _extract_csv(self, content):
        rows = load_csv(content)
        claims = []
        interest_total = Decimal("0")
        for idx, row in enumerate(rows):
            narration = str(row.get("Narration") or row.get("Description") or row.get("Particulars") or "")
            credit = parse_decimal(row.get("Credit") or row.get("Deposit") or row.get("Amount"))
            if credit is not None and re.search(r"\binterest\b|int\.?\s*cr", narration, re.I):
                interest_total += credit
                claims.append(ExtractedClaim("OTHER_INCOME.BANK_INTEREST.TRANSACTION", "money", money_value(credit), SourceLocation(original_text=str(row)), Decimal("0.96"), entity_key=f"ROW_{idx}"))
        if interest_total:
            claims.append(ExtractedClaim("OTHER_INCOME.BANK_INTEREST.TOTAL", "money", money_value(interest_total), SourceLocation(original_text="Sum of identified interest-credit rows"), Decimal("0.96"), validations=[{"code": "SUM_OF_TRANSACTION_ROWS", "status": "PASS"}]))
        return AdapterResult(self.code, self.version, self.document_type, claims, [] if claims else ["No explicit interest credits were found."], {"row_count": len(rows)})

    def _extract_pdf(self, content):
        pages = pdf_pages(content)
        claims = []
        total = Decimal("0")
        pattern = re.compile(r"(?:interest|int\.?\s*cr)[^\n]*?([0-9][0-9,]*\.[0-9]{2})", re.I)
        for page in pages:
            for block in page["blocks"]:
                for match in pattern.finditer(block["text"]):
                    value = parse_decimal(match.group(1))
                    if value is not None:
                        total += value
                        claims.append(ExtractedClaim("OTHER_INCOME.BANK_INTEREST.TRANSACTION", "money", money_value(value), SourceLocation(page["page_index"], block["bbox"], match.group(0)), Decimal("0.80"), entity_key=f"P{page['page_index']}_{len(claims)}"))
        if total:
            claims.append(ExtractedClaim("OTHER_INCOME.BANK_INTEREST.TOTAL", "money", money_value(total), SourceLocation(original_text="Sum of PDF interest matches"), Decimal("0.80")))
        return AdapterResult(self.code, self.version, self.document_type, claims, ["PDF bank-statement extraction requires CA confirmation of all interest entries."], {"page_count": len(pages)})
