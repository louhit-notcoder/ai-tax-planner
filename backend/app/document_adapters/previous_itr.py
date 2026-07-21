from __future__ import annotations

from decimal import Decimal

from .base import AdapterResult, DocumentAdapter, ExtractedClaim, SourceLocation, load_json


class PreviousITRJSONAdapter(DocumentAdapter):
    code = "PREVIOUS_ITR_JSON"
    version = "3.0.0"
    document_type = "PREVIOUS_ITR"

    def supports(self, filename, mime_type, content):
        if not filename.lower().endswith(".json"):
            return Decimal("0")
        try:
            payload = load_json(content)
        except Exception:
            return Decimal("0")
        keys = str(payload)[:5000]
        return Decimal("0.90") if "CreationInfo" in keys and ("ITR1" in keys or "ITR2" in keys or "ITR3" in keys or "ITR4" in keys) else Decimal("0.10")

    def extract(self, filename, mime_type, content):
        payload = load_json(content)
        root_key = next((key for key in ["ITR1", "ITR2", "ITR3", "ITR4"] if key in payload), None)
        if not root_key:
            # Some utility files wrap under ITR.
            itr = payload.get("ITR", {}) if isinstance(payload, dict) else {}
            root_key = next((key for key in itr if key.startswith("ITR")), None)
            data = itr.get(root_key, {}) if root_key else {}
        else:
            data = payload[root_key]
        claims = [ExtractedClaim("PRIOR_RETURN.RAW_SCHEDULES", "object", {"form": root_key, "payload": data}, SourceLocation(original_text="Official-style prior year JSON import"), Decimal("0.99"), entity_key="PRIOR_YEAR")]
        return AdapterResult(self.code, self.version, self.document_type, claims, [] if root_key else ["ITR root was not recognised."], {"form": root_key})
