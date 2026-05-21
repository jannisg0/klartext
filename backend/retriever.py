"""Hybrid retrieval: dense (BGE-M3 + ChromaDB) + sparse (BM25) + RRF.

The retriever holds references to the embedder, the ChromaDB collection
and the in-memory BM25 index. It supports optional query expansion (via
the helper LLM) and party-level filtering on both branches. Final hits
are materialized by a single ``collection.get(ids=...)`` so the caller
gets text + metadata back, not just ids.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from backend.bm25_index import Bm25Index


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    score: float
    text: str
    metadata: dict


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class ChromaCollection(Protocol):
    def query(
        self,
        *,
        query_embeddings: Sequence[Sequence[float]],
        n_results: int,
        where: dict | None = None,
    ) -> dict: ...

    def get(self, *, ids: Sequence[str]) -> dict: ...


class LLM(Protocol):
    def generate(self, prompt: str) -> str: ...


def party_of(chunk_id: str) -> str:
    """Idempotent IDs encode party as the first underscore-delimited token."""
    return chunk_id.split("_", 1)[0]


def rrf_fuse(rank_lists: Sequence[Sequence[str]], *, k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion. Score per id = sum of 1 / (k + rank)."""
    scores: dict[str, float] = {}
    for ranking in rank_lists:
        for rank, cid in enumerate(ranking, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


_LIST_PREFIX_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


def _strip_list_prefix(line: str) -> str:
    return _LIST_PREFIX_RE.sub("", line).strip()


_EXPANSION_PROMPT = (
    "Generiere 2 alternative deutsche Formulierungen dieser Frage. "
    "Eine pro Zeile, keine Nummerierung, keine Anführungszeichen.\n"
    "Frage: {query}"
)


def expand_query(query: str, *, llm: LLM, enabled: bool = True) -> list[str]:
    """Return [query, alt1, alt2]. With enabled=False, returns [query] only."""
    if not enabled:
        return [query]
    raw = llm.generate(_EXPANSION_PROMPT.format(query=query))
    alts: list[str] = []
    for line in raw.splitlines():
        stripped = _strip_list_prefix(line)
        if stripped:
            alts.append(stripped)
    return [query, *alts[:2]]


@dataclass
class HybridRetriever:
    collection: ChromaCollection
    bm25: Bm25Index
    embedder: Embedder

    def dense_search(
        self,
        query: str,
        *,
        top_k: int,
        party_filter: Sequence[str] | None = None,
    ) -> list[str]:
        embedding = self.embedder.embed([query])[0]
        where = {"party": {"$in": list(party_filter)}} if party_filter else None
        result = self.collection.query(query_embeddings=[embedding], n_results=top_k, where=where)
        ids = result.get("ids", [[]])
        return list(ids[0]) if ids else []

    def sparse_search(
        self,
        query: str,
        *,
        top_k: int,
        party_filter: Sequence[str] | None = None,
    ) -> list[str]:
        # When filtering, over-fetch so we still have ~top_k after the filter.
        fetch = top_k * 4 if party_filter else top_k
        raw = self.bm25.search(query, top_k=fetch)
        ids = [cid for cid, _ in raw]
        if party_filter:
            party_set = set(party_filter)
            ids = [cid for cid in ids if party_of(cid) in party_set]
        return ids[:top_k]

    def retrieve(
        self,
        queries: Sequence[str],
        *,
        top_k: int = 30,
        dense_top_k: int = 30,
        sparse_top_k: int = 30,
        party_filter: Sequence[str] | None = None,
    ) -> list[Hit]:
        rank_lists: list[list[str]] = []
        for q in queries:
            rank_lists.append(self.dense_search(q, top_k=dense_top_k, party_filter=party_filter))
            rank_lists.append(self.sparse_search(q, top_k=sparse_top_k, party_filter=party_filter))

        fused = rrf_fuse(rank_lists)[:top_k]
        if not fused:
            return []

        ids = [cid for cid, _ in fused]
        score_by_id = dict(fused)
        got = self.collection.get(ids=ids)
        text_by_id = dict(zip(got["ids"], got["documents"], strict=True))
        meta_by_id = dict(zip(got["ids"], got["metadatas"], strict=True))

        hits: list[Hit] = []
        for cid in ids:
            if cid not in text_by_id:
                continue
            hits.append(
                Hit(
                    chunk_id=cid,
                    score=score_by_id[cid],
                    text=text_by_id[cid],
                    metadata=meta_by_id[cid],
                )
            )
        return hits
