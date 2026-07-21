from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db_models import LegalSource
from .embeddings import cosine_similarity, embedding_client


@dataclass(frozen=True)
class LegalPassage:
    source_id: str
    title: str
    source_type: str
    act_namespace: str
    section_or_rule: str | None
    official_url: str
    applicable_periods: list[str]
    passage: str
    content_location: str | None
    source_document_hash: str | None
    score: float


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9]+", text.lower()) if len(token) > 2}


def _candidate_rows(db: Session, *, query: str, act_namespace: str, maximum: int = 250) -> list[LegalSource]:
    base = select(LegalSource).where(
        LegalSource.review_status == "APPROVED",
        LegalSource.superseded.is_(False),
        LegalSource.act_namespace == act_namespace,
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        document = func.to_tsvector(
            "english",
            func.coalesce(LegalSource.title, "") + " " + func.coalesce(LegalSource.section_or_rule, "") + " " + LegalSource.content_text,
        )
        query_vector = func.websearch_to_tsquery("english", query)
        base = base.where(document.op("@@")(query_vector)).order_by(func.ts_rank_cd(document, query_vector).desc())
    return list(db.scalars(base.limit(maximum)))


def search_approved_sources(db: Session, *, query: str, tax_period: str, act_namespace: str, limit: int = 8) -> list[LegalPassage]:
    query_tokens = _tokens(query)
    embedded_query = embedding_client.embed(query)
    rows = _candidate_rows(db, query=query, act_namespace=act_namespace)
    # A strict PostgreSQL FTS query can return no row for section numbers or unusual
    # legal phrasing; retry approved rows and rank in Python without changing filters.
    if not rows:
        rows = list(db.scalars(select(LegalSource).where(
            LegalSource.review_status == "APPROVED",
            LegalSource.superseded.is_(False),
            LegalSource.act_namespace == act_namespace,
        ).limit(500)))
    results: list[LegalPassage] = []
    for row in rows:
        if row.applicable_periods and tax_period not in row.applicable_periods:
            continue
        text = f"{row.title} {row.section_or_rule or ''} {row.content_text}"
        tokens = _tokens(text)
        overlap = len(query_tokens & tokens)
        phrase_bonus = 2.0 if query.lower() in text.lower() else 0.0
        lexical = overlap / max(1, len(query_tokens)) + phrase_bonus
        semantic = cosine_similarity(embedded_query.vector if embedded_query else None, row.embedding_json)
        if lexical <= 0 and semantic <= 0:
            continue
        score = lexical * 0.65 + semantic * 0.35
        results.append(LegalPassage(
            row.id,
            row.title,
            row.source_type,
            row.act_namespace,
            row.section_or_rule,
            row.official_url,
            row.applicable_periods,
            row.content_text[:2200],
            row.content_location,
            row.source_document_hash,
            score,
        ))
    return sorted(results, key=lambda item: item.score, reverse=True)[:limit]
