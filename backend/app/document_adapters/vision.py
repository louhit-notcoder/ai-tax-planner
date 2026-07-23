"""Vision-model document extraction.

The deterministic tax engine still owns every rupee of arithmetic. This module
only uses a vision-capable model where models are genuinely strong — *reading*
a real Form 16 / broker note / bank statement into structured fields — and it
emits the exact same evidence-linked `ExtractedClaim` contract the regex
adapters use, so every field still flows through the human maker-checker review
gate with a confidence score and a page reference.

The model returns strict JSON only; it never computes totals. Anything it cannot
read confidently comes back low-confidence (or absent) and is caught in review.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Protocol

import requests

import fitz

# Vision models drift on very long documents and cost scales with pages, so cap
# how many pages we send. Form 16 / broker / bank PDFs are well within this.
MAX_PAGES = 12
# Render at ~150 DPI: sharp enough for small statement digits, small enough to send.
RENDER_ZOOM = 2.0


def render_document_images(content: bytes, mime_type: str, max_pages: int = MAX_PAGES) -> list[dict[str, Any]]:
    """Return page images as [{"page_index": int, "b64": str, "media_type": str}].

    PDFs are rasterised page by page. Image uploads (scanned docs, phone photos)
    pass through as a single page, which is exactly the case brittle text
    extraction cannot handle at all.
    """
    mime = (mime_type or "").lower()
    if mime.startswith("image/"):
        return [{"page_index": 0, "b64": base64.b64encode(content).decode("ascii"), "media_type": mime}]

    images: list[dict[str, Any]] = []
    doc = fitz.open(stream=content, filetype="pdf")
    try:
        matrix = fitz.Matrix(RENDER_ZOOM, RENDER_ZOOM)
        for index, page in enumerate(doc):
            if index >= max_pages:
                break
            pixmap = page.get_pixmap(matrix=matrix)
            images.append({
                "page_index": index,
                "b64": base64.b64encode(pixmap.tobytes("png")).decode("ascii"),
                "media_type": "image/png",
            })
    finally:
        doc.close()
    return images


class VisionExtractionClient(Protocol):
    """Seam so adapters can be unit-tested with a fake client (no network)."""

    def enabled(self) -> bool: ...

    def extract(self, images: list[dict[str, Any]], instruction: str, schema_hint: str) -> list[dict[str, Any]]: ...


class OpenRouterVisionClient:
    """Vision extraction over OpenRouter. Mirrors the assistant client's config.

    Uses a dedicated `OPENROUTER_VISION_MODEL` when set, otherwise falls back to
    the assistant model (e.g. google/gemini-2.5-flash, which is vision-capable).
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.model = os.getenv("OPENROUTER_VISION_MODEL") or os.getenv("OPENROUTER_ASSISTANT_MODEL", "")
        self.base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.require_zdr = os.getenv("OPENROUTER_REQUIRE_ZDR", "false").lower() == "true"

    def enabled(self) -> bool:
        return bool(self.api_key and self.model)

    def extract(self, images: list[dict[str, Any]], instruction: str, schema_hint: str) -> list[dict[str, Any]]:
        if not self.enabled():
            raise RuntimeError("Vision extraction model is not configured")
        content: list[dict[str, Any]] = [{"type": "text", "text": schema_hint}]
        for image in images:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{image['media_type']};base64,{image['b64']}"},
            })
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Title": "Green Papaya Document Extraction",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": content},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "provider": {"data_collection": "deny", "zdr": self.require_zdr},
            },
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        text = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        return parse_model_fields(text)


def parse_model_fields(text: str) -> list[dict[str, Any]]:
    """Parse the model's JSON reply into a list of field rows.

    Tolerant of a bare list, a ```json fence, or a {"fields": [...]} envelope so a
    minor format wobble degrades to 'nothing extracted, review flagged' rather
    than a 500.
    """
    if not text:
        return []
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return []
    if isinstance(data, dict):
        data = data.get("fields") or data.get("claims") or []
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]
