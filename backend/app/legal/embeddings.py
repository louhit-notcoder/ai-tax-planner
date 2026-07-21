from __future__ import annotations

import math
from dataclasses import dataclass

import requests

from ..config import get_settings


@dataclass(frozen=True)
class EmbeddingResult:
    vector: list[float]
    model: str


class EmbeddingClient:
    """Optional OpenAI-compatible embedding client.

    Retrieval remains available through approved-source full-text search when no
    embedding provider is configured. No taxpayer content is sent here; this client
    is intended for public official legal sources and legal search queries only.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.embedding_base_url
        self.api_key = settings.embedding_api_key
        self.model = settings.embedding_model

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def embed(self, text: str) -> EmbeddingResult | None:
        if not self.enabled:
            return None
        response = requests.post(
            f"{self.base_url.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "input": text[:16_000]},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        vector = payload["data"][0]["embedding"]
        return EmbeddingResult([float(item) for item in vector], str(payload.get("model") or self.model))


def cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if not norm_left or not norm_right:
        return 0.0
    return dot / (norm_left * norm_right)


embedding_client = EmbeddingClient()
