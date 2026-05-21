"""Tests for the contextual enrichment helper.

The enricher must:
- prefix each chunk with one model-generated context sentence
- cache by SHA256(section_path + text) so re-ingests skip the LLM
- be no-op when ``enabled=False`` (config switch)
- be tolerant of leading/trailing whitespace and quotes from the model
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.chunker import Chunk
from backend.enricher import ContextEnricher, build_enrichment_prompt, chunk_cache_key


def _chunk(text: str, section_path: str = "Wirtschaft > Steuerpolitik") -> Chunk:
    return Chunk(
        chunk_id="spd_p1_c0",
        party="spd",
        text=text,
        section_path=section_path,
        page=1,
        chunk_idx=0,
    )


class _FakeLLM:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[str] = []

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.responses.pop(0)


def test_build_prompt_contains_section_path_and_chunk():
    prompt = build_enrichment_prompt(section_path="A > B", chunk_text="Wir wollen X.")

    assert "A > B" in prompt
    assert "Wir wollen X." in prompt
    assert "EINEN Satz" in prompt


def test_cache_key_stable_for_same_input():
    c1 = _chunk("Hello world.", "Wirtschaft > Steuerpolitik")
    c2 = _chunk("Hello world.", "Wirtschaft > Steuerpolitik")
    c3 = _chunk("Hello world.", "Wirtschaft > Arbeitsmarkt")

    assert chunk_cache_key(c1) == chunk_cache_key(c2)
    assert chunk_cache_key(c1) != chunk_cache_key(c3)
    assert len(chunk_cache_key(c1)) == 64


def test_enricher_prefixes_chunk_with_generated_context(tmp_path: Path):
    llm = _FakeLLM(responses=["Dieser Abschnitt befasst sich mit der Vermoegensteuer."])
    enricher = ContextEnricher(llm=llm, cache_path=tmp_path / "cache.json", enabled=True)
    chunk = _chunk("Vermoegen ab 1 Million sollen besteuert werden.")

    out = enricher.enrich(chunk)

    assert out.context == "Dieser Abschnitt befasst sich mit der Vermoegensteuer."
    assert out.text.startswith("Dieser Abschnitt befasst sich mit der Vermoegensteuer.")
    assert "Vermoegen ab 1 Million" in out.text
    assert out.chunk_id == chunk.chunk_id


def test_enricher_hits_cache_on_second_call(tmp_path: Path):
    llm = _FakeLLM(responses=["Kontextsatz eins."])
    enricher = ContextEnricher(llm=llm, cache_path=tmp_path / "cache.json", enabled=True)
    chunk = _chunk("Body text.")

    first = enricher.enrich(chunk)
    second = enricher.enrich(chunk)

    assert first.context == second.context
    assert len(llm.calls) == 1


def test_enricher_cache_persists_across_instances(tmp_path: Path):
    cache_path = tmp_path / "cache.json"
    llm_a = _FakeLLM(responses=["Persisted context."])
    ContextEnricher(llm=llm_a, cache_path=cache_path, enabled=True).enrich(_chunk("Body."))

    llm_b = _FakeLLM(responses=[])  # would raise IndexError if called
    out = ContextEnricher(llm=llm_b, cache_path=cache_path, enabled=True).enrich(_chunk("Body."))

    assert out.context == "Persisted context."
    assert llm_b.calls == []


def test_enricher_strips_whitespace_and_quotes(tmp_path: Path):
    llm = _FakeLLM(responses=['  "Mit Anfuehrungszeichen."  \n'])
    enricher = ContextEnricher(llm=llm, cache_path=tmp_path / "cache.json", enabled=True)

    out = enricher.enrich(_chunk("Body."))

    assert out.context == "Mit Anfuehrungszeichen."


def test_enricher_disabled_returns_empty_context(tmp_path: Path):
    llm = _FakeLLM(responses=[])  # must not be called
    enricher = ContextEnricher(llm=llm, cache_path=tmp_path / "cache.json", enabled=False)

    out = enricher.enrich(_chunk("Body text."))

    assert out.context == ""
    assert out.text == "Body text."
    assert llm.calls == []


def test_enrich_batch_returns_same_order(tmp_path: Path):
    llm = _FakeLLM(responses=["ctx-a", "ctx-b", "ctx-c"])
    enricher = ContextEnricher(llm=llm, cache_path=tmp_path / "cache.json", enabled=True)
    chunks = [
        _chunk("aaa", "S > X"),
        _chunk("bbb", "S > Y"),
        _chunk("ccc", "S > Z"),
    ]

    out = enricher.enrich_batch(chunks)

    assert [o.context for o in out] == ["ctx-a", "ctx-b", "ctx-c"]
    assert [o.chunk_id for o in out] == [c.chunk_id for c in chunks]


def test_enricher_raises_on_empty_llm_response(tmp_path: Path):
    llm = _FakeLLM(responses=["   "])
    enricher = ContextEnricher(llm=llm, cache_path=tmp_path / "cache.json", enabled=True)

    with pytest.raises(ValueError):
        enricher.enrich(_chunk("Body."))
