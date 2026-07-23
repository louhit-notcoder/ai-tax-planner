from __future__ import annotations

from decimal import Decimal

from .ais import AISJSONAdapter
from .banks import BankStatementAdapter
from .base import AdapterResult, DocumentAdapter
from .brokers import BrokerCapitalGainsAdapter
from .form16 import Form16Adapter
from .llm_adapters import BankStatementPDFAdapter, BrokerCapitalGainsPDFAdapter, Form16LLMAdapter, USBrokerageForeignAssetPDFAdapter
from .previous_itr import PreviousITRJSONAdapter
from .tis_26as import Form26ASAdapter, TISAdapter


class AdapterRegistry:
    def __init__(self, adapters: list[DocumentAdapter] | None = None):
        # LLM-assisted adapters score 0 when the vision model is unconfigured, so
        # the deterministic regex/JSON adapters below remain the fallback.
        self.adapters = adapters or [
            Form16LLMAdapter(), BrokerCapitalGainsPDFAdapter(), BankStatementPDFAdapter(), USBrokerageForeignAssetPDFAdapter(),
            Form16Adapter(), AISJSONAdapter(), TISAdapter(), Form26ASAdapter(),
            BankStatementAdapter(), BrokerCapitalGainsAdapter(), PreviousITRJSONAdapter(),
        ]

    def classify(self, filename: str, mime_type: str, content: bytes) -> tuple[DocumentAdapter | None, Decimal]:
        scored = [(adapter.supports(filename, mime_type, content), adapter) for adapter in self.adapters]
        score, adapter = max(scored, key=lambda item: item[0], default=(Decimal("0"), None))
        return (adapter if score >= Decimal("0.50") else None), score

    def extract(self, filename: str, mime_type: str, content: bytes) -> AdapterResult:
        adapter, score = self.classify(filename, mime_type, content)
        if adapter is None:
            return AdapterResult("UNSUPPORTED", "1.0.0", "UNKNOWN", warnings=["No production adapter recognised this document."], metadata={"classification_score": str(score)})
        result = adapter.extract(filename, mime_type, content)
        result.metadata["classification_score"] = str(score)
        return result
