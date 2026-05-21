"""Tests for the hybrid retriever module.

Covers:
- RRF fusion (math + edge cases)
- expand_query (LLM output parsing)
- HybridRetriever.retrieve (dense + sparse + party filter + materialize)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from backend.bm25_index import Bm25Index
from backend.retriever import (
    Hit,
    HybridRetriever,
    expand_query,
    party_of,
    rrf_fuse,
)

# ---------- RRF ----------


def test_rrf_fuse_single_list_preserves_order():
    fused = rrf_fuse([["a", "b", "c"]])
    ids = [cid for cid, _ in fused]
    assert ids == ["a", "b", "c"]


def test_rrf_fuse_combines_two_lists_promoting_overlap():
    fused = rrf_fuse([["a", "b", "c"], ["b", "a", "d"]])
    ids = [cid for cid, _ in fused]
    # 'b' is at rank 2 and rank 1; 'a' at rank 1 and rank 2 — equal scores.
    # Order between a and b is implementation-defined; both must be top 2.
    assert set(ids[:2]) == {"a", "b"}
    assert "c" in ids and "d" in ids


def test_rrf_fuse_uses_constant_k():
    # rank 1 with k=60 → 1/61, with k=10 → 1/11. Same id, different score.
    f60 = rrf_fuse([["a"]], k=60)
    f10 = rrf_fuse([["a"]], k=10)
    assert f60[0][1] == pytest.approx(1 / 61)
    assert f10[0][1] == pytest.approx(1 / 11)


def test_rrf_fuse_empty_input_returns_empty():
    assert rrf_fuse([]) == []
    assert rrf_fuse([[], []]) == []


def test_party_of_extracts_first_token():
    assert party_of("spd_p12_c3") == "spd"
    assert party_of("cdu_p1_c0") == "cdu"


# ---------- Query expansion ----------


class _FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt: str | None = None

    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response


def test_expand_query_returns_three_queries_in_order():
    llm = _FakeLLM(
        "Wie steht die SPD zu Vermögen?\nWelche Position vertritt die SPD zur Vermögensteuer?"
    )

    queries = expand_query("Was sagt SPD zur Vermögensteuer?", llm=llm)

    assert queries[0] == "Was sagt SPD zur Vermögensteuer?"
    assert len(queries) == 3
    assert all(isinstance(q, str) and q for q in queries)
    assert "alternative" in (llm.last_prompt or "").lower()


def test_expand_query_truncates_extra_lines():
    llm = _FakeLLM("alt 1\nalt 2\nalt 3\nalt 4")

    queries = expand_query("orig", llm=llm)

    assert queries == ["orig", "alt 1", "alt 2"]


def test_expand_query_strips_numbering_and_bullets():
    llm = _FakeLLM("1. erste alt\n- zweite alt")

    queries = expand_query("orig", llm=llm)

    assert queries == ["orig", "erste alt", "zweite alt"]


def test_expand_query_returns_original_only_when_disabled():
    llm = _FakeLLM("should not be called")

    queries = expand_query("orig", llm=llm, enabled=False)

    assert queries == ["orig"]
    assert llm.last_prompt is None


# ---------- HybridRetriever ----------


@dataclass
class _FakeEmbedder:
    embed_calls: list[list[str]] = field(default_factory=list)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        batch = list(texts)
        self.embed_calls.append(batch)
        # Deterministic 3-d vector based on text length.
        return [[float(len(t)), float(len(t) % 5), 1.0] for t in batch]


@dataclass
class _FakeChroma:
    """Fake Chroma collection with manifest-style data."""

    by_id: dict[str, tuple[str, dict]]
    dense_responses: list[list[str]]  # per query, in call order
    query_calls: list[dict] = field(default_factory=list)

    def query(
        self,
        *,
        query_embeddings: Sequence[Sequence[float]],
        n_results: int,
        where: dict | None = None,
    ) -> dict:
        self.query_calls.append(
            {"n_results": n_results, "where": where, "embeddings": list(query_embeddings)}
        )
        ids = self.dense_responses.pop(0)[:n_results]
        return {"ids": [ids]}

    def get(self, *, ids: Sequence[str]) -> dict:
        ids = [cid for cid in ids if cid in self.by_id]
        return {
            "ids": list(ids),
            "documents": [self.by_id[cid][0] for cid in ids],
            "metadatas": [self.by_id[cid][1] for cid in ids],
        }


def _build_index_and_chroma():
    docs = {
        "spd_p1_c0": "Wir wollen die Vermögensteuer wieder einführen.",
        "spd_p2_c0": "Mindestlohn auf 15 Euro.",
        "cdu_p1_c0": "Wir senken Steuern für Mittelschicht.",
        "gruene_p1_c0": "Klimaschutz ist Sicherheitspolitik.",
    }
    bm25 = Bm25Index.build(docs)
    by_id = {
        cid: (
            text,
            {
                "party": cid.split("_", 1)[0],
                "section_path": "S > X",
                "page": 1,
                "chunk_id": cid,
                "context": "",
            },
        )
        for cid, text in docs.items()
    }
    return docs, bm25, by_id


def test_retriever_dense_search_returns_ids_only():
    _, bm25, by_id = _build_index_and_chroma()
    chroma = _FakeChroma(by_id=by_id, dense_responses=[["spd_p1_c0", "cdu_p1_c0"]])
    embedder = _FakeEmbedder()
    r = HybridRetriever(collection=chroma, bm25=bm25, embedder=embedder)

    ids = r.dense_search("Vermögensteuer", top_k=2)

    assert ids == ["spd_p1_c0", "cdu_p1_c0"]
    assert embedder.embed_calls == [["Vermögensteuer"]]
    assert chroma.query_calls[0]["n_results"] == 2


def test_retriever_dense_search_applies_party_filter():
    _, bm25, by_id = _build_index_and_chroma()
    chroma = _FakeChroma(by_id=by_id, dense_responses=[["spd_p1_c0"]])
    r = HybridRetriever(collection=chroma, bm25=bm25, embedder=_FakeEmbedder())

    r.dense_search("Vermögensteuer", top_k=5, party_filter=["spd"])

    assert chroma.query_calls[0]["where"] == {"party": {"$in": ["spd"]}}


def test_retriever_sparse_search_uses_bm25_and_filters_by_party():
    _, bm25, by_id = _build_index_and_chroma()
    chroma = _FakeChroma(by_id=by_id, dense_responses=[])
    r = HybridRetriever(collection=chroma, bm25=bm25, embedder=_FakeEmbedder())

    ids = r.sparse_search("Vermögensteuer", top_k=10, party_filter=["spd"])

    assert all(party_of(cid) == "spd" for cid in ids)
    assert "spd_p1_c0" in ids


def test_retriever_retrieve_returns_materialized_hits():
    _, bm25, by_id = _build_index_and_chroma()
    # 2 queries → 4 lists (2 dense + 2 sparse).
    chroma = _FakeChroma(
        by_id=by_id,
        dense_responses=[
            ["spd_p1_c0", "cdu_p1_c0"],
            ["spd_p1_c0", "gruene_p1_c0"],
        ],
    )
    r = HybridRetriever(collection=chroma, bm25=bm25, embedder=_FakeEmbedder())

    hits = r.retrieve(
        ["Vermögensteuer?", "Was zu Vermögen?"],
        top_k=3,
        dense_top_k=2,
        sparse_top_k=2,
    )

    assert all(isinstance(h, Hit) for h in hits)
    assert hits[0].chunk_id == "spd_p1_c0"
    assert hits[0].metadata["party"] == "spd"
    assert "Vermögensteuer" in hits[0].text
    assert len(hits) <= 3


def test_retrieve_returns_empty_when_all_lists_empty():
    _build_index_and_chroma()
    chroma = _FakeChroma(by_id={}, dense_responses=[[]])
    r = HybridRetriever(
        collection=chroma, bm25=Bm25Index.build({"x": "x"}), embedder=_FakeEmbedder()
    )

    hits = r.retrieve(["no match xyz123notpresent"], top_k=5, dense_top_k=2, sparse_top_k=2)

    assert hits == []
