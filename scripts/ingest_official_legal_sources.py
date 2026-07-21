#!/usr/bin/env python3
"""Download official legal sources into reviewable, chunked RAG records.

Nothing is APPROVED unless --approve is explicitly supplied by an authorised human
after checking the official source, content hash and extracted text.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import requests
from pypdf import PdfReader
from sqlalchemy import select

from app.database import SessionLocal, create_all
from app.db_models import LegalSource
from app.legal.embeddings import embedding_client

REGISTRY = ROOT / "backend" / "rules" / "legal" / "official_sources_registry.json"


def extract_pages(content: bytes, content_type: str) -> list[tuple[str, str]]:
    if "pdf" in content_type.lower() or content.startswith(b"%PDF"):
        reader = PdfReader(io.BytesIO(content))
        return [(f"page:{index + 1}", page.extract_text() or "") for index, page in enumerate(reader.pages)]
    text = content.decode("utf-8-sig", errors="replace")
    if "html" in content_type.lower() or "<html" in text[:500].lower():
        text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
    return [("document", re.sub(r"\s+", " ", text))]


def chunks(pages: list[tuple[str, str]], size: int = 2200, overlap: int = 250):
    index = 0
    for location, raw in pages:
        text = re.sub(r"\s+", " ", raw).strip()
        start = 0
        while start < len(text):
            piece = text[start:start + size].strip()
            if piece:
                yield index, location, piece
                index += 1
            if start + size >= len(text):
                break
            start += size - overlap


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approve", action="store_true", help="Mark chunks approved only after human verification")
    parser.add_argument("--embed", action="store_true", help="Generate embeddings using configured provider")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    if args.embed and not embedding_client.enabled:
        raise SystemExit("Embedding provider is not configured")
    create_all()
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    with SessionLocal() as db:
        for item in registry["sources"]:
            response = requests.get(item["official_url"], timeout=args.timeout, headers={"User-Agent": "GreenPapaya-LegalSync/3.0"})
            response.raise_for_status()
            document_hash = hashlib.sha256(response.content).hexdigest()
            page_data = extract_pages(response.content, response.headers.get("content-type", ""))
            count = 0
            for chunk_index, location, text in chunks(page_data):
                chunk_hash = hashlib.sha256((document_hash + "|" + location + "|" + text).encode("utf-8")).hexdigest()
                existing = db.scalar(select(LegalSource).where(LegalSource.source_hash == chunk_hash))
                if existing:
                    continue
                embedded = embedding_client.embed(text) if args.embed else None
                row = LegalSource(
                    source_type=item["source_type"], title=item["title"], act_namespace=item["act_namespace"],
                    section_or_rule=item.get("section_or_rule"), applicable_periods=item.get("applicable_periods", []),
                    official_url=item["official_url"], source_hash=chunk_hash, source_document_hash=document_hash,
                    chunk_index=chunk_index, content_location=location,
                    review_status="APPROVED" if args.approve else "PENDING", content_text=text,
                    superseded=False, embedding_json=embedded.vector if embedded else None,
                    embedding_model=embedded.model if embedded else None,
                )
                db.add(row)
                count += 1
            print({"title": item["title"], "status": "APPROVED" if args.approve else "PENDING", "document_sha256": document_hash, "new_chunks": count})
        db.commit()


if __name__ == "__main__":
    main()
