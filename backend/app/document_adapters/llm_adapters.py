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
from datetime import date, datetime
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


# Grandfathering under section 112A only applies to equity/equity-MF acquired on
# or before this date; FMV as on 31-Jan-2018 is otherwise irrelevant.
GRANDFATHER_DATE = date(2018, 1, 31)
_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d-%b-%Y", "%b %d, %Y", "%Y/%m/%d", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S")


class BrokerCapitalGainsPDFAdapter(LLMDocumentAdapter):
    """Transaction-level capital-gains extraction from a broker PDF tax P&L.

    Brokers give a PDF far more often than a clean CSV/Excel, and the taxable
    figure depends on *per-transaction* facts (holding period, STT, 112A
    grandfathering) — so we extract each trade as its own reviewable object claim
    that maps onto the engine's CapitalGainTransaction, never a pre-summed total.
    """

    code = "BROKER_CAPITAL_GAINS_PDF_LLM"
    version = "3.0.0"
    document_type = "BROKER_CAPITAL_GAINS"

    instruction = (
        "You read Indian broker capital-gains / realised P&L statements (Zerodha, Groww, "
        "ICICI Direct, etc.) for a Chartered Accountant. Report every disposal transaction "
        "exactly as printed. Never sum, net, or compute gains yourself; copy the numbers as shown."
    )

    # Columns requested per transaction row.
    _COLUMNS = [
        ("symbol", "security / scrip / scheme name"),
        ("isin", "ISIN if shown (e.g. INE009A01021)"),
        ("acquisition_date", "buy / acquisition / entry date"),
        ("transfer_date", "sell / transfer / exit date"),
        ("sale_consideration", "sell/sale value or consideration in rupees (plain number)"),
        ("actual_cost", "buy/purchase/acquisition cost in rupees (plain number)"),
        ("transfer_expenses", "charges/brokerage/expenses in rupees if shown, else omit"),
        ("fmv_2018_01_31", "grandfathered / fair market value as on 31-Jan-2018 if shown, else omit"),
        ("realized_gain", "the broker's own stated realised profit/loss for the row (for cross-check)"),
        ("stt_paid", "whether STT was paid: true/false"),
    ]

    _TOKENS = ("capital gain", "tradewise", "realized", "realised", "profit and loss", "p&l", "pnl", "sale value", "buy value", "holding period", "short term", "long term", "grandfathered")

    def _detect(self, filename: str, mime_type: str, content: bytes) -> Decimal:
        mime = (mime_type or "").lower()
        name = (filename or "").lower()
        if "pdf" in mime or name.endswith(".pdf"):
            try:
                text = "\n".join(page["text"] for page in pdf_pages(content)[:4]).lower()
            except Exception:
                text = ""
            hits = sum(1 for token in self._TOKENS if token in text)
            if hits >= 2:
                return min(Decimal("0.86") + Decimal("0.03") * hits, Decimal("0.98"))
        if mime.startswith("image/") and re.search(r"capital|gain|pnl|tradewise", name):
            return Decimal("0.82")
        return Decimal("0")

    def _schema_hint(self) -> str:
        cols = "\n".join(f"- {code}: {desc}" for code, desc in self._COLUMNS)
        return (
            "Extract EVERY capital-gains transaction (one object per disposal row) from the attached pages.\n"
            "Columns per transaction:\n" + cols +
            "\n\nReturn strict JSON: {\"items\": [{<columns above>, \"page_index\": <0-based>, "
            "\"confidence\": <0..1>}]}. Use plain rupee numbers (no symbols/commas). Omit a column you "
            "cannot read for a row. Never invent or compute a value; if a whole row is unreadable, skip it."
        )

    def extract(self, filename: str, mime_type: str, content: bytes) -> AdapterResult:
        images = render_document_images(content, mime_type)
        try:
            rows = self.client.extract(images, self.instruction, self._schema_hint())
        except Exception as exc:
            return AdapterResult(self.code, self.version, self.document_type, [], [f"Vision extraction failed: {exc}"], {"page_count": len(images), "extraction": "llm", "failed": True})
        warnings: list[str] = []
        claims = self.transactions_from_rows(rows, page_count=len(images), warnings=warnings)
        if not claims and not warnings:
            warnings.append("No complete capital-gains transactions were recognised in this document.")
        return AdapterResult(self.code, self.version, self.document_type, claims, warnings, {"page_count": len(images), "extraction": "llm", "raw_row_count": len(rows), "transaction_count": len(claims)})

    def transactions_from_rows(self, rows: list[dict[str, Any]], *, page_count: int, warnings: list[str]) -> list[ExtractedClaim]:
        claims: list[ExtractedClaim] = []
        skipped = 0
        for idx, row in enumerate(rows):
            sale = parse_decimal(row.get("sale_consideration"))
            cost = parse_decimal(row.get("actual_cost"))
            acq = self._date(row.get("acquisition_date"))
            transfer = self._date(row.get("transfer_date"))
            if sale is None or cost is None or acq is None or transfer is None:
                skipped += 1
                continue
            expenses = parse_decimal(row.get("transfer_expenses")) or Decimal("0")
            symbol = str(row.get("symbol") or f"ROW_{idx}").strip()
            isin = str(row.get("isin") or "").strip().upper()

            values: dict[str, Any] = {
                "asset_type": self._asset_type(isin, symbol),
                "description": symbol,
                "acquisition_date": acq,
                "transfer_date": transfer,
                "sale_consideration": format(sale, "f"),
                "actual_cost": format(cost, "f"),
                "transfer_expenses": format(expenses, "f"),
                "stt_paid_on_transfer": self._bool(row.get("stt_paid")),
            }
            if isin:
                values["isin"] = isin

            validations: list[dict[str, Any]] = []
            fmv = parse_decimal(row.get("fmv_2018_01_31"))
            if fmv is not None and date.fromisoformat(acq) <= GRANDFATHER_DATE:
                values["fmv_2018_01_31"] = format(fmv, "f")
                validations.append({"code": "GRANDFATHERED_112A", "status": "PASS"})

            # Cross-check the broker's stated realised gain against sale-cost-expenses.
            # A mismatch usually means a column was misread — flag it for the CA.
            realized = parse_decimal(row.get("realized_gain"))
            if realized is not None:
                computed = sale - cost - expenses
                tolerance = max(Decimal("1"), abs(realized) * Decimal("0.01"))
                status = "PASS" if abs(computed - realized) <= tolerance else "REVIEW"
                validations.append({"code": "REALIZED_GAIN_CROSSCHECK", "status": status, "computed": format(computed, "f"), "stated": format(realized, "f")})
                if status == "REVIEW":
                    warnings.append(f"Row {idx + 1} ({symbol}): computed gain {computed} does not match the statement's {realized}; verify the columns.")

            confidence = self._clamp_confidence(row.get("confidence"))
            page_index = self._page_index(row.get("page_index"), page_count)
            claims.append(ExtractedClaim(
                field_code="CAPITAL_GAIN.TRANSACTION",
                value_type="object",
                value=values,
                source=SourceLocation(page_index=page_index, bounding_box=None, original_text=None),
                confidence=confidence,
                validations=validations,
                entity_key=f"TRADE_{idx}_{symbol}"[:160],
            ))
        if skipped:
            warnings.append(f"{skipped} row(s) were skipped because a required field (sale, cost, or a date) was missing; review the source.")
        return claims

    @staticmethod
    def _asset_type(isin: str, symbol: str) -> str:
        # Indian ISIN convention: INF... = mutual fund, INE... = company equity.
        if isin.startswith("INF"):
            return "EQUITY_MUTUAL_FUND"
        if isin.startswith("INE"):
            return "LISTED_EQUITY"
        lowered = symbol.lower()
        if "fund" in lowered or "scheme" in lowered or "mf" in lowered:
            return "EQUITY_MUTUAL_FUND"
        return "LISTED_EQUITY"

    @staticmethod
    def _date(raw: Any) -> str | None:
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
        return None

    @staticmethod
    def _bool(raw: Any) -> bool | None:
        if raw is None or str(raw).strip() == "":
            return None
        return str(raw).strip().lower() in {"yes", "y", "true", "1", "paid", "t"}


class BankStatementPDFAdapter(LLMDocumentAdapter):
    """Interest-income extraction from a bank statement PDF/scan.

    Pulls each interest *credit* line (savings/FD interest paid by the bank) with
    its date and amount, and computes the total in code (never trusting the model
    to add). Bank statements are the least reliable source — AIS usually reports
    interest more completely — so the total is emitted at the lowest line
    confidence and every line stays individually reviewable.
    """

    code = "BANK_STATEMENT_PDF_LLM"
    version = "3.0.0"
    document_type = "BANK_STATEMENT"

    instruction = (
        "You read Indian bank account statements for a Chartered Accountant. Identify ONLY "
        "interest credited by the bank to the account holder (savings-account interest, "
        "fixed/term-deposit interest). Ignore all other credits (salary, transfers, refunds, "
        "reversals). Report exactly what is printed; never total the figures yourself."
    )

    _COLUMNS = [
        ("date", "value/transaction date of the interest credit"),
        ("description", "the narration/description text of the interest credit"),
        ("amount", "the interest amount credited in rupees (plain number)"),
    ]

    _TOKENS = ("statement", "account number", "a/c no", "transaction date", "narration", "closing balance", "ifsc")

    def _detect(self, filename: str, mime_type: str, content: bytes) -> Decimal:
        mime = (mime_type or "").lower()
        name = (filename or "").lower()
        if "pdf" in mime or name.endswith(".pdf"):
            try:
                text = "\n".join(page["text"] for page in pdf_pages(content)[:3]).lower()
            except Exception:
                text = ""
            hits = sum(1 for token in self._TOKENS if token in text)
            has_bank = any(b in text for b in ("bank", "hdfc", "icici", "state bank", "sbi", "axis", "kotak"))
            if has_bank and hits >= 2:
                return min(Decimal("0.87") + Decimal("0.02") * hits, Decimal("0.97"))
        if mime.startswith("image/") and re.search(r"bank|statement|passbook", name):
            return Decimal("0.80")
        return Decimal("0")

    def _schema_hint(self) -> str:
        cols = "\n".join(f"- {code}: {desc}" for code, desc in self._COLUMNS)
        return (
            "From the attached bank-statement pages, return EVERY interest-credit line (and nothing else).\n"
            "Columns per line:\n" + cols +
            "\n\nReturn strict JSON: {\"items\": [{<columns above>, \"page_index\": <0-based>, "
            "\"confidence\": <0..1>}]}. Plain rupee numbers, no symbols/commas. If there are no interest "
            "credits, return {\"items\": []}. Never invent a line or compute a total."
        )

    def extract(self, filename: str, mime_type: str, content: bytes) -> AdapterResult:
        images = render_document_images(content, mime_type)
        try:
            rows = self.client.extract(images, self.instruction, self._schema_hint())
        except Exception as exc:
            return AdapterResult(self.code, self.version, self.document_type, [], [f"Vision extraction failed: {exc}"], {"page_count": len(images), "extraction": "llm", "failed": True})
        claims: list[ExtractedClaim] = []
        total = Decimal("0")
        confidences: list[Decimal] = []
        for idx, row in enumerate(rows):
            amount = parse_decimal(row.get("amount"))
            if amount is None or amount <= 0:
                continue
            confidence = self._clamp_confidence(row.get("confidence"))
            confidences.append(confidence)
            total += amount
            page_index = self._page_index(row.get("page_index"), len(images))
            quote = str(row.get("description") or "").strip() or None
            claims.append(ExtractedClaim(
                field_code="OTHER_INCOME.BANK_INTEREST.TRANSACTION",
                value_type="money",
                value=money_value(amount),
                source=SourceLocation(page_index=page_index, bounding_box=None, original_text=quote),
                confidence=confidence,
                entity_key=f"INT_{idx}",
            ))
        warnings = ["Bank-statement interest is less complete than AIS; confirm against AIS and Form 26AS."]
        if claims:
            # Total is computed here from the line items, never read from the model.
            claims.append(ExtractedClaim(
                field_code="OTHER_INCOME.BANK_INTEREST.TOTAL",
                value_type="money",
                value=money_value(total),
                source=SourceLocation(original_text="Sum of extracted interest-credit lines"),
                confidence=min(confidences) if confidences else Decimal("0.5"),
                validations=[{"code": "SUM_OF_TRANSACTION_ROWS", "status": "PASS", "line_count": len(confidences)}],
            ))
        else:
            warnings.append("No interest credits were identified in this statement.")
        return AdapterResult(self.code, self.version, self.document_type, claims, warnings, {"page_count": len(images), "extraction": "llm", "interest_line_count": len(confidences), "interest_total": format(total, "f")})


class USBrokerageForeignAssetPDFAdapter(LLMDocumentAdapter):
    """Foreign assets + income from a US brokerage statement (Fidelity, Schwab,
    Vanguard, Robinhood, etc.), for Schedule FA / FSI / FTC.

    A resident who holds a US brokerage account must report it in Schedule FA and
    the dividends/interest in Schedule FSI (with Form 67 for the US tax withheld).
    This reads the account and its income into FOREIGN_ASSET / FOREIGN_INCOME.ITEM
    facts. Statement amounts are in USD — the adapter carries them through as a
    draft and flags CURRENCY_CONVERSION_REQUIRED so the CA applies the prescribed
    SBI TT buying rate before finalising. The model never converts or totals.
    """

    code = "US_BROKERAGE_FA_PDF_LLM"
    version = "3.0.0"
    document_type = "US_BROKERAGE_STATEMENT"

    instruction = (
        "You read US brokerage / investment statements (Fidelity, Charles Schwab, Vanguard, "
        "Robinhood, Morgan Stanley, E*TRADE, etc.) for an Indian Chartered Accountant handling "
        "foreign-asset (Schedule FA) reporting. Report exactly what is printed, in USD. Never "
        "convert currency, never total figures, never guess."
    )

    fields = [
        FieldSpec("institution", "text", "brokerage/institution name (e.g. Fidelity)"),
        FieldSpec("account_number_masked", "text", "account number, masked (last 4 digits ok)"),
        FieldSpec("closing_value_usd", "money", "total account/portfolio value at period end, in USD"),
        FieldSpec("peak_value_usd", "money", "highest/peak account value during the period, in USD, if shown"),
        FieldSpec("dividends_usd", "money", "total dividends received during the period, in USD"),
        FieldSpec("interest_usd", "money", "total interest received during the period, in USD"),
        FieldSpec("foreign_tax_withheld_usd", "money", "US tax withheld on dividends/income, in USD"),
    ]

    _TOKENS = ("fidelity", "charles schwab", "schwab", "vanguard", "robinhood", "morgan stanley",
               "e*trade", "etrade", "td ameritrade", "1099", "ordinary dividends", "cusip",
               "brokerage", "portfolio value", "settlement date")

    def _detect(self, filename: str, mime_type: str, content: bytes) -> Decimal:
        mime = (mime_type or "").lower()
        name = (filename or "").lower()
        broker_names = ("fidelity", "schwab", "vanguard", "robinhood", "e*trade", "etrade", "td ameritrade", "morgan stanley")
        if "pdf" in mime or name.endswith(".pdf"):
            try:
                text = "\n".join(page["text"] for page in pdf_pages(content)[:4]).lower()
            except Exception:
                text = ""
            has_broker = any(b in text for b in broker_names)
            hits = sum(1 for token in self._TOKENS if token in text)
            # Require a US-broker signal (or a 1099 + dividends combo) to avoid
            # colliding with the Indian capital-gains statement adapter.
            if has_broker and hits >= 2:
                return min(Decimal("0.90") + Decimal("0.02") * hits, Decimal("0.98"))
            if ("1099" in text and "dividend" in text) and "$" in text:
                return Decimal("0.86")
        if mime.startswith("image/") and any(b in name for b in broker_names):
            return Decimal("0.82")
        return Decimal("0")

    def extract(self, filename: str, mime_type: str, content: bytes) -> AdapterResult:
        images = render_document_images(content, mime_type)
        try:
            rows = self.client.extract(images, self.instruction, self._schema_hint())
        except Exception as exc:
            return AdapterResult(self.code, self.version, self.document_type, [], [f"Vision extraction failed: {exc}"], {"page_count": len(images), "extraction": "llm", "failed": True})
        # Read the flat fields into a name->(amount/text, confidence, page) map.
        values: dict[str, Any] = {}
        confidences: list[Decimal] = []
        page_hint: int | None = None
        for row in rows:
            code = str(row.get("field_code", "")).strip()
            if code not in {f.field_code for f in self.fields}:
                continue
            raw = row.get("value")
            if raw is None or str(raw).strip() == "":
                continue
            values[code] = raw
            confidences.append(self._clamp_confidence(row.get("confidence")))
            if page_hint is None:
                page_hint = self._page_index(row.get("page_index"), len(images))
        return self._build_foreign_facts(values, confidences, page_hint, len(images))

    def _build_foreign_facts(self, values: dict[str, Any], confidences: list[Decimal], page: int | None, page_count: int) -> AdapterResult:
        institution = str(values.get("institution") or "US Brokerage").strip()
        acct = str(values.get("account_number_masked") or "").strip()
        closing = parse_decimal(values.get("closing_value_usd"))
        peak = parse_decimal(values.get("peak_value_usd"))
        dividends = parse_decimal(values.get("dividends_usd")) or Decimal("0")
        interest = parse_decimal(values.get("interest_usd")) or Decimal("0")
        withheld = parse_decimal(values.get("foreign_tax_withheld_usd")) or Decimal("0")
        confidence = min(confidences) if confidences else Decimal("0.5")
        entity = re.sub(r"[^A-Z0-9]+", "_", (institution + "_" + acct).upper()).strip("_")[:80] or "US_BROKERAGE"
        source = SourceLocation(page_index=page, bounding_box=None, original_text="Amounts as printed in USD")
        usd_review = {"code": "CURRENCY_CONVERSION_REQUIRED", "status": "REVIEW", "note": "USD draft — apply SBI TT buying rate to INR before finalising."}

        claims: list[ExtractedClaim] = []
        # Schedule FA — the account itself (Table A2: foreign custodial account).
        asset: dict[str, Any] = {
            "asset_id": f"FA_{entity}",
            "schedule_fa_table": "A2",
            "country_code": "US",
            "institution_or_entity": institution,
            "account_number_masked": acct or None,
            "income_derived_inr": format(dividends + interest, "f"),
            "ownership_type": "SINGLE",
        }
        if closing is not None:
            asset["closing_value_inr"] = format(closing, "f")
            asset["peak_value_inr"] = format(peak if peak is not None else closing, "f")
        claims.append(ExtractedClaim(field_code="FOREIGN_ASSET", value_type="object", value=asset, source=source, confidence=confidence, validations=[usd_review], entity_key=f"FA_{entity}"))

        # Schedule FSI/FTC — dividends and interest as foreign income.
        for income_type, amount in (("DIVIDEND", dividends), ("INTEREST", interest)):
            if amount <= 0:
                continue
            item: dict[str, Any] = {
                "item_id": f"FSI_{entity}_{income_type}",
                "country_code": "US",
                "income_type": income_type,
                "gross_income_inr": format(amount, "f"),
                "foreign_tax_paid_inr": format(withheld if income_type == "DIVIDEND" else Decimal("0"), "f"),
                "form_67_filed": False,
            }
            claims.append(ExtractedClaim(field_code="FOREIGN_INCOME.ITEM", value_type="object", value=item, source=source, confidence=confidence, validations=[usd_review], entity_key=item["item_id"]))

        warnings = [
            "US brokerage detected: Schedule FA (foreign asset) and Schedule FSI/FTC apply for a resident; Form 67 is required to claim credit for US tax withheld.",
            "All amounts are in USD — apply the prescribed SBI TT buying rate to convert to INR before accepting these facts.",
        ]
        if closing is None:
            warnings.append("Account value was not identified; Schedule FA needs the peak and closing balances.")
        return AdapterResult(self.code, self.version, self.document_type, claims, warnings, {"page_count": page_count, "extraction": "llm", "currency": "USD", "foreign_asset_count": 1, "foreign_income_count": len(claims) - 1})
