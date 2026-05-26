"""Tests for the log-probability reranker.

``LogProbReranker`` is tested by injecting a fake ``ChatCompletionAPI``
that returns controlled log-prob responses without a real inference
server.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast

import pytest
from openai.resources.chat.completions import Completions

from backend.reranker import LogProbReranker, RerankResult
from backend.retriever import Hit


def _hit(chunk_id: str, text: str = "body") -> Hit:
    return Hit(
        chunk_id=chunk_id,
        score=0.0,
        text=text,
        metadata={"party": chunk_id.split("_", 1)[0]},
    )


def _logprob_response(token: str, logprob: float) -> Any:
    """Build a SimpleNamespace mimicking an OpenAI non-streaming response with log-probs.

    Includes a complementary Ja/Nein token so the normalized score equals
    the input probability: score = p / (p + (1-p)) = p.
    """
    p = math.exp(logprob)
    complement_token = "Nein" if token.strip().lower() in {"ja", "yes", "▁ja", "▁yes"} else "Ja"
    complement_lp = math.log(max(1.0 - p, 1e-10))
    primary = SimpleNamespace(token=token, logprob=logprob)
    complement = SimpleNamespace(token=complement_token, logprob=complement_lp)
    content_item = SimpleNamespace(top_logprobs=[primary, complement])
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                logprobs=SimpleNamespace(content=[content_item]),
            )
        ]
    )


def _no_logprobs_response() -> Any:
    return SimpleNamespace(choices=[SimpleNamespace(logprobs=None)])


@dataclass
class _FakeCompletions:
    """Maps chunk text → (token, logprob). Tracks all calls."""

    score_map: dict[str, tuple[str, float]]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def create(self, *, model, messages, stream, max_tokens, temperature, **kwargs):
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        content = messages[-1]["content"]
        # Match against the "Text: <chunk>" portion to avoid false substring hits
        # from single-character texts that appear in the German prompt template.
        for text, (token, lp) in self.score_map.items():
            if f"Text: {text}" in content:
                return _logprob_response(token, lp)
        return _no_logprobs_response()


def _ja_lp(prob: float) -> float:
    """Convert probability to log-probability."""
    return math.log(prob)


def _reranker(fake: _FakeCompletions, *, threshold: float = 0.0) -> LogProbReranker:
    return LogProbReranker(completions=cast(Completions, fake), model="test", threshold=threshold)


# ─── core ranking ────────────────────────────────────────────────────────────


def test_rerank_sorts_hits_by_ja_probability_descending():
    fake = _FakeCompletions(
        score_map={
            "low body": ("Ja", _ja_lp(0.4)),
            "mid body": ("Ja", _ja_lp(0.6)),
            "high body": ("Ja", _ja_lp(0.9)),
        }
    )
    reranker = _reranker(fake)

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
    assert result.hits[0].score == pytest.approx(0.9, abs=1e-6)
    assert result.below_threshold is False


def test_rerank_keeps_only_top_k():
    fake = _FakeCompletions(
        score_map={
            "a": ("Ja", _ja_lp(0.9)),
            "b": ("Ja", _ja_lp(0.8)),
            "c": ("Ja", _ja_lp(0.7)),
            "d": ("Ja", _ja_lp(0.6)),
            "e": ("Ja", _ja_lp(0.5)),
        }
    )
    reranker = _reranker(fake)

    result = reranker.rerank(
        query="q",
        hits=[_hit(f"x_p1_c{i}", t) for i, t in enumerate("abcde")],
        top_k=3,
    )

    assert len(result.hits) == 3
    assert [h.chunk_id for h in result.hits] == ["x_p1_c0", "x_p1_c1", "x_p1_c2"]


def test_rerank_signals_below_threshold_when_top_score_too_low():
    fake = _FakeCompletions(
        score_map={
            "a": ("Ja", _ja_lp(0.1)),
            "b": ("Ja", _ja_lp(0.05)),
        }
    )
    reranker = _reranker(fake, threshold=0.3)

    result = reranker.rerank(
        query="q",
        hits=[_hit("a_p1_c0", "a"), _hit("b_p1_c0", "b")],
        top_k=5,
    )

    assert result.hits == []
    assert result.below_threshold is True


def test_rerank_drops_individual_hits_below_threshold():
    fake = _FakeCompletions(
        score_map={
            "a": ("Ja", _ja_lp(0.9)),
            "b": ("Ja", _ja_lp(0.2)),
            "c": ("Ja", _ja_lp(0.4)),
        }
    )
    reranker = _reranker(fake, threshold=0.3)

    result = reranker.rerank(
        query="q",
        hits=[_hit("a_p1_c0", "a"), _hit("b_p1_c0", "b"), _hit("c_p1_c0", "c")],
        top_k=5,
    )

    ids = [h.chunk_id for h in result.hits]
    assert ids == ["a_p1_c0", "c_p1_c0"]
    assert result.below_threshold is False


def test_rerank_empty_hits_returns_empty_not_below_threshold():
    fake = _FakeCompletions(score_map={})
    reranker = _reranker(fake, threshold=0.3)

    result = reranker.rerank(query="q", hits=[], top_k=5)

    assert result == RerankResult(hits=[], below_threshold=False)


def test_rerank_preserves_metadata_on_rescored_hits():
    fake = _FakeCompletions(score_map={"body": ("Ja", _ja_lp(0.7))})
    reranker = _reranker(fake)

    hit = Hit(chunk_id="spd_p1_c0", score=0.0, text="body", metadata={"party": "spd", "page": 7})
    result = reranker.rerank(query="q", hits=[hit], top_k=1)

    assert result.hits[0].metadata == {"party": "spd", "page": 7}
    assert result.hits[0].score == pytest.approx(0.7, abs=1e-6)


# ─── log-prob extraction ─────────────────────────────────────────────────────


def test_score_returns_zero_when_no_logprobs_in_response():
    class _NoLogprobs:
        def create(self, **kwargs):
            return _no_logprobs_response()

    reranker = LogProbReranker(
        completions=cast(Completions, _NoLogprobs()), model="test", threshold=0.0
    )
    result = reranker.rerank(query="q", hits=[_hit("a_p1_c0", "body")], top_k=1)

    # Score of 0.0 < threshold 0.0 is false (equal is not below), so hit stays.
    assert result.hits[0].score == pytest.approx(0.0)


def test_score_accepts_ja_with_space_marker():
    """Tokenizers may prepend a space-marker (▁) to the 'Ja' token."""
    fake = _FakeCompletions(score_map={"body": ("▁Ja", _ja_lp(0.8))})
    reranker = _reranker(fake)

    result = reranker.rerank(query="q", hits=[_hit("a_p1_c0", "body")], top_k=1)

    assert result.hits[0].score == pytest.approx(0.8, abs=1e-6)


def test_score_passes_max_tokens_one_to_api():
    fake = _FakeCompletions(score_map={"body": ("Ja", _ja_lp(0.5))})
    reranker = _reranker(fake)

    reranker.rerank(query="q", hits=[_hit("a_p1_c0", "body")], top_k=1)

    assert all(c["max_tokens"] == 1 for c in fake.calls)


def test_score_includes_query_and_chunk_text_in_prompt():
    fake = _FakeCompletions(score_map={"chunk text": ("Ja", _ja_lp(0.6))})
    reranker = LogProbReranker(completions=fake, model="test", threshold=0.0)

    reranker.rerank(query="my question", hits=[_hit("a_p1_c0", "chunk text")], top_k=1)

    prompt = fake.calls[0]["messages"][-1]["content"]
    assert "Frage: my question" in prompt
    assert "Text: chunk text" in prompt
