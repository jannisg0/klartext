"""Tests for the cross-encoder reranker.

The scorer is injected so we don't load bge-reranker-v2-m3 in tests.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from backend.reranker import CrossEncoderReranker, RerankResult
from backend.retriever import Hit


def _hit(chunk_id: str, text: str = "body") -> Hit:
    return Hit(
        chunk_id=chunk_id, score=0.0, text=text, metadata={"party": chunk_id.split("_", 1)[0]}
    )


@dataclass
class _FakeScorer:
    """Scores pairs based on a lookup keyed by chunk text."""

    scores: dict[str, float]
    pairs_seen: list[tuple[str, str]] = field(default_factory=list)

    def score(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        pairs = list(pairs)
        self.pairs_seen.extend(pairs)
        return [self.scores.get(text, 0.0) for _, text in pairs]


def test_rerank_sorts_hits_by_score_descending():
    scorer = _FakeScorer({"low body": 0.4, "mid body": 0.6, "high body": 0.9})
    reranker = CrossEncoderReranker(scorer=scorer, threshold=0.0)

    result = reranker.rerank(
        query="q",
        hits=[
            _hit("a_p1_c0", "low body"),
            _hit("b_p1_c0", "high body"),
            _hit("c_p1_c0", "mid body"),
        ],
        top_k=3,
    )

    ids = [h.chunk_id for h in result.hits]
    assert ids == ["b_p1_c0", "c_p1_c0", "a_p1_c0"]
    assert result.hits[0].score == 0.9
    assert result.below_threshold is False


def test_rerank_keeps_only_top_k():
    scorer = _FakeScorer({"a": 0.9, "b": 0.8, "c": 0.7, "d": 0.6, "e": 0.5})
    reranker = CrossEncoderReranker(scorer=scorer, threshold=0.0)

    result = reranker.rerank(
        query="q",
        hits=[_hit(f"x_p1_c{i}", t) for i, t in enumerate("abcde")],
        top_k=3,
    )

    assert len(result.hits) == 3
    assert [h.chunk_id for h in result.hits] == ["x_p1_c0", "x_p1_c1", "x_p1_c2"]


def test_rerank_signals_below_threshold_when_top_too_low():
    scorer = _FakeScorer({"a": 0.1, "b": 0.05})
    reranker = CrossEncoderReranker(scorer=scorer, threshold=0.3)

    result = reranker.rerank(
        query="q",
        hits=[_hit("a_p1_c0", "a"), _hit("b_p1_c0", "b")],
        top_k=5,
    )

    assert result.hits == []
    assert result.below_threshold is True


def test_rerank_drops_individual_hits_below_threshold():
    scorer = _FakeScorer({"a": 0.9, "b": 0.2, "c": 0.4})
    reranker = CrossEncoderReranker(scorer=scorer, threshold=0.3)

    result = reranker.rerank(
        query="q",
        hits=[_hit("a_p1_c0", "a"), _hit("b_p1_c0", "b"), _hit("c_p1_c0", "c")],
        top_k=5,
    )

    ids = [h.chunk_id for h in result.hits]
    assert ids == ["a_p1_c0", "c_p1_c0"]
    assert result.below_threshold is False


def test_rerank_empty_hits_returns_empty_not_below_threshold():
    scorer = _FakeScorer({})
    reranker = CrossEncoderReranker(scorer=scorer, threshold=0.3)

    result = reranker.rerank(query="q", hits=[], top_k=5)

    assert result == RerankResult(hits=[], below_threshold=False)


def test_rerank_passes_query_text_pairs_to_scorer():
    scorer = _FakeScorer({"body1": 0.5, "body2": 0.6})
    reranker = CrossEncoderReranker(scorer=scorer, threshold=0.0)

    reranker.rerank(
        query="my query",
        hits=[_hit("a_p1_c0", "body1"), _hit("b_p1_c0", "body2")],
        top_k=2,
    )

    assert scorer.pairs_seen == [("my query", "body1"), ("my query", "body2")]


def test_rerank_preserves_metadata_on_rewrap():
    scorer = _FakeScorer({"body": 0.7})
    reranker = CrossEncoderReranker(scorer=scorer, threshold=0.0)

    hit = Hit(chunk_id="spd_p1_c0", score=0.0, text="body", metadata={"party": "spd", "page": 7})
    result = reranker.rerank(query="q", hits=[hit], top_k=1)

    assert result.hits[0].metadata == {"party": "spd", "page": 7}
    assert result.hits[0].score == 0.7
