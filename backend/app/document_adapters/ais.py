from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from .base import AdapterResult, DocumentAdapter, ExtractedClaim, SourceLocation, load_json, money_value, parse_decimal


class AISJSONAdapter(DocumentAdapter):
    code = "AIS_JSON"
    version = "3.0.0"
    document_type = "AIS"

    CATEGORY_MAP = {
        "salary": "RECONCILIATION.AIS.SALARY",
        "interest": "RECONCILIATION.AIS.INTEREST",
        "dividend": "RECONCILIATION.AIS.DIVIDEND",
        "sale of securities": "RECONCILIATION.AIS.SECURITIES_SALE",
        "purchase of securities": "RECONCILIATION.AIS.SECURITIES_PURCHASE",
        "tds": "RECONCILIATION.AIS.TDS",
        "tcs": "RECONCILIATION.AIS.TCS",
        "rent": "RECONCILIATION.AIS.RENT",
        "foreign remittance": "RECONCILIATION.AIS.FOREIGN_REMITTANCE",
    }

    def supports(self, filename, mime_type, content):
        if not filename.lower().endswith(".json") and "json" not in mime_type.lower():
            return Decimal("0")
        try:
            obj = load_json(content)
        except Exception:
            return Decimal("0")
        text = str(obj).lower()[:10000]
        return Decimal("0.95") if any(key in text for key in ["annual information statement", "informationcode", "derivedvalue", "ais"]) else Decimal("0.20")

    def extract(self, filename, mime_type, content):
        payload = load_json(content)
        records = []
        self._walk(payload, records, path="$")
        claims: list[ExtractedClaim] = []
        seen: set[tuple[str, str, str]] = set()
        totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for record in records:
            category = self._category(record)
            amount = self._amount(record)
            if not category or amount is None:
                continue
            info_code = str(record.get("informationCode") or record.get("infoCode") or record.get("code") or "UNKNOWN")
            reporting_entity = str(record.get("reportingEntityName") or record.get("deductorName") or record.get("sourceName") or "UNKNOWN")
            transaction_id = str(record.get("transactionId") or record.get("acknowledgementNumber") or record.get("srNo") or record.get("_path"))
            dedupe = (info_code, reporting_entity, transaction_id)
            if dedupe in seen:
                continue
            seen.add(dedupe)
            field_code = self.CATEGORY_MAP[category]
            entity_key = f"{info_code}:{reporting_entity}"[:160]
            claims.append(ExtractedClaim(
                field_code=field_code,
                value_type="money",
                value=money_value(amount),
                source=SourceLocation(original_text=f"AIS JSON path {record.get('_path')}: {record}"),
                confidence=Decimal("0.98"),
                validations=[{"code": "AIS_TRANSACTION_DEDUPED", "status": "PASS", "transaction_id": transaction_id}],
                entity_key=entity_key,
            ))
            totals[field_code] += amount
        warnings = [] if records else ["No transaction-level AIS records were recognised."]
        return AdapterResult(self.code, self.version, self.document_type, claims, warnings, {"record_count": len(records), "accepted_count": len(claims), "totals": {k: str(v) for k, v in totals.items()}})

    def _walk(self, obj: Any, records: list[dict], path: str):
        if isinstance(obj, dict):
            enriched = dict(obj)
            enriched["_path"] = path
            if self._amount(enriched) is not None and self._category(enriched):
                records.append(enriched)
            for key, value in obj.items():
                self._walk(value, records, f"{path}.{key}")
        elif isinstance(obj, list):
            for idx, value in enumerate(obj):
                self._walk(value, records, f"{path}[{idx}]")

    def _category(self, record):
        text = " ".join(str(record.get(key, "")) for key in ["informationCode", "informationDescription", "description", "category", "transactionType"]).lower()
        for key in self.CATEGORY_MAP:
            if key in text:
                return key
        return None

    @staticmethod
    def _amount(record):
        priority = ["derivedValue", "reportedValue", "amount", "transactionAmount", "totalAmount", "tdsAmount", "tcsAmount"]
        for key in priority:
            value = record.get(key)
            if isinstance(value, (int, float, str)):
                parsed = parse_decimal(value)
                if parsed is not None:
                    return parsed
        return None
