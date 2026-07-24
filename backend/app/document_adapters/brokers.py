from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .base import AdapterResult, DocumentAdapter, ExtractedClaim, SourceLocation, load_csv, money_value, parse_decimal


class BrokerCapitalGainsAdapter(DocumentAdapter):
    code = "BROKER_CAPITAL_GAINS_GENERIC"
    version = "3.0.0"
    document_type = "BROKER_CAPITAL_GAINS"

    def supports(self, filename, mime_type, content):
        name = filename.lower()
        if not (name.endswith(".csv") or name.endswith(".txt")):
            return Decimal("0")
        if any(token in name for token in ["zerodha", "groww", "capital", "pnl", "gain", "trade", "tax", "stock", "upstox", "icici", "hdfc", "angel"]):
            return Decimal("0.85")
        try:
            sample = content[:4096].decode("utf-8-sig", errors="replace").lower()
            if any(k in sample for k in ["symbol", "scrip", "buy date", "sell date", "sale value", "buy value", "isin", "stt", "acquisition"]):
                return Decimal("0.80")
        except Exception:
            pass
        return Decimal("0.25")

    def extract(self, filename, mime_type, content):
        rows = load_csv(content)
        claims = []
        warnings = []
        for idx, row in enumerate(rows):
            symbol = str(row.get("Symbol") or row.get("Scrip Name") or row.get("Scheme Name") or row.get("Security") or f"ROW_{idx}")
            buy_date = self._date(row.get("Buy Date") or row.get("Acquisition Date") or row.get("Purchase Date"))
            sell_date = self._date(row.get("Sell Date") or row.get("Transfer Date") or row.get("Sale Date"))
            sale = parse_decimal(row.get("Sale Value") or row.get("Sell Value") or row.get("Sale Consideration"))
            cost = parse_decimal(row.get("Buy Value") or row.get("Cost of Acquisition") or row.get("Purchase Value"))
            expenses = parse_decimal(row.get("Transfer Expenses") or row.get("Expenses")) or Decimal("0")
            if sale is None or cost is None or buy_date is None or sell_date is None:
                continue
            entity = f"TRADE_{idx}_{symbol}"[:160]
            values = {
                "asset_type": "EQUITY_MUTUAL_FUND" if "fund" in symbol.lower() or "scheme" in " ".join(row.keys()).lower() else "LISTED_EQUITY",
                "description": symbol,
                "acquisition_date": buy_date,
                "transfer_date": sell_date,
                "sale_consideration": format(sale, "f"),
                "actual_cost": format(cost, "f"),
                "transfer_expenses": format(expenses, "f"),
                "stt_paid_on_transfer": self._bool(row.get("STT Paid") or row.get("STT")),
            }
            claims.append(ExtractedClaim("CAPITAL_GAIN.TRANSACTION", "object", values, SourceLocation(original_text=str(row)), Decimal("0.94"), validations=[{"code": "REQUIRED_TRANSACTION_FIELDS", "status": "PASS"}], entity_key=entity))
        if not claims:
            warnings.append("No complete transaction rows were recognised. Export a trade-level tax P&L CSV.")
        return AdapterResult(self.code, self.version, self.document_type, claims, warnings, {"row_count": len(rows), "transaction_count": len(claims)})

    @staticmethod
    def _date(raw):
        if not raw:
            return None
        text = str(raw).strip()
        for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d-%b-%Y"]:
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                pass
        return None

    @staticmethod
    def _bool(raw):
        if raw is None:
            return None
        return str(raw).strip().lower() in {"yes", "y", "true", "1", "paid"}
