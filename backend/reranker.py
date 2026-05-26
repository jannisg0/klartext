"""Log-probability reranker via OpenAI Chat Completions.

Re-scores the top-N hits from hybrid retrieval by asking the LLM to
judge each (query, chunk) pair with a single "Ja/Nein" token and
reading the log-probability of the affirmative first token as the
relevance score.  This replaces the cross-encoder (bge-reranker) with
the model already running on the inference server, keeping the memory
footprint flat.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

from backend.retriever import Hit


@dataclass(frozen=True)
class RerankResult:
    hits: list[Hit]
    below_threshold: bool


class ChatCompletionAPI(Protocol):
    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        stream: bool,
        max_tokens: int,
        temperature: float,
        **kwargs: Any,
    ) -> Any: ...


_RERANK_PROMPT = (
    "Ist folgender Textabschnitt relevant für diese Frage?\n\n"
    "Frage: {query}\n\nText: {text}\n\n"
    "Antworte nur mit 'Ja' oder 'Nein'."
)

# mlx-lm and Ollama may return the token with a leading space-marker.
_JA_TOKENS = frozenset({"ja", "yes", "▁ja", "▁yes"})


@dataclass
class LogProbReranker:
    """Reranker that scores hits via log-probs from a chat completion API."""

    completions: ChatCompletionAPI
    model: str
    threshold: float = 0.3

    def rerank(self, *, query: str, hits: list[Hit], top_k: int = 5) -> RerankResult:
        if not hits:
            return RerankResult(hits=[], below_threshold=False)

        scored = sorted(
            (
                Hit(
                    chunk_id=h.chunk_id,
                    score=self._score(query, h.text),
                    text=h.text,
                    metadata=h.metadata,
                )
                for h in hits
            ),
            key=lambda h: h.score,
            reverse=True,
        )
        top_pool = scored[:top_k]

        if top_pool[0].score < self.threshold:
            return RerankResult(hits=[], below_threshold=True)

        return RerankResult(
            hits=[h for h in top_pool if h.score >= self.threshold],
            below_threshold=False,
        )

    def _score(self, query: str, text: str) -> float:
        response = self.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": _RERANK_PROMPT.format(query=query, text=text),
                }
            ],
            stream=False,
            max_tokens=1,
            temperature=0.0,
            logprobs=True,
            top_logprobs=5,
        )
        choice = response.choices[0]
        if not choice.logprobs or not choice.logprobs.content:
            return 0.0
        for token_lp in choice.logprobs.content[0].top_logprobs:
            if token_lp.token.strip().lower() in _JA_TOKENS:
                return math.exp(token_lp.logprob)
        return 0.0
