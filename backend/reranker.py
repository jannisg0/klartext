"""Cross-encoder reranking.

Wraps a cross-encoder scorer (``bge-reranker-v2-m3`` in production) to
re-score the top-N hits from hybrid retrieval and keep only the top-K
above a relevance threshold. When the best post-rerank score falls
under the threshold, ``below_threshold=True`` is reported so the API
can signal "no good match" to the user rather than feeding the LLM
weak context.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from backend.retriever import Hit


class CrossEncoderScorer(Protocol):
    def score(self, pairs: Sequence[tuple[str, str]]) -> Sequence[float]: ...


@dataclass(frozen=True)
class RerankResult:
    hits: list[Hit]
    below_threshold: bool


@dataclass
class CrossEncoderReranker:
    scorer: CrossEncoderScorer
    threshold: float = 0.3

    def rerank(self, *, query: str, hits: list[Hit], top_k: int = 5) -> RerankResult:
        if not hits:
            return RerankResult(hits=[], below_threshold=False)

        pairs = [(query, h.text) for h in hits]
        scores = list(self.scorer.score(pairs))
        ranked = sorted(zip(hits, scores, strict=True), key=lambda x: x[1], reverse=True)

        rescored = [
            Hit(chunk_id=h.chunk_id, score=float(s), text=h.text, metadata=h.metadata)
            for h, s in ranked
        ]
        top_pool = rescored[:top_k]

        if top_pool[0].score < self.threshold:
            return RerankResult(hits=[], below_threshold=True)

        kept = [h for h in top_pool if h.score >= self.threshold]
        return RerankResult(hits=kept, below_threshold=False)
