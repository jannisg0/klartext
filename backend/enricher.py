"""Contextual enrichment for retrieved chunks.

Each chunk gets a single sentence prepended that tells the embedder
where the chunk lives in the document tree. This is the Anthropic
"Contextual Retrieval" pattern. We use the cheap helper model
(qwen3:4b) and cache by SHA256(section_path + text) so re-ingests of
the same chunk are free.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from backend.chunker import Chunk

_PROMPT_TEMPLATE = (
    "Document-Kontext: {section_path}\n"
    "Chunk: {chunk}\n"
    "Schreibe EINEN Satz der erklärt wo dieser Chunk im Wahlprogramm "
    "sitzt. Nur den Satz, sonst nichts."
)


class _LLM(Protocol):
    def generate(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class EnrichedChunk:
    chunk_id: str
    party: str
    text: str
    section_path: str
    page: int
    chunk_idx: int
    context: str


def build_enrichment_prompt(*, section_path: str, chunk_text: str) -> str:
    return _PROMPT_TEMPLATE.format(section_path=section_path, chunk=chunk_text)


def chunk_cache_key(chunk: Chunk) -> str:
    """Stable SHA256 key over (section_path, text)."""
    payload = f"{chunk.section_path}\x00{chunk.text}".encode()
    return hashlib.sha256(payload).hexdigest()


def _clean(response: str) -> str:
    return response.strip().strip('"').strip("'").strip()


class ContextEnricher:
    def __init__(self, *, llm: _LLM, cache_path: Path, enabled: bool = True) -> None:
        self._llm = llm
        self._cache_path = Path(cache_path)
        self._enabled = enabled
        self._cache: dict[str, str] = self._load_cache()

    def _load_cache(self) -> dict[str, str]:
        if self._cache_path.exists():
            return json.loads(self._cache_path.read_text(encoding="utf-8"))
        return {}

    def _save_cache(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def enrich(self, chunk: Chunk) -> EnrichedChunk:
        if not self._enabled:
            return self._wrap(chunk, context="")

        key = chunk_cache_key(chunk)
        cached = self._cache.get(key)
        if cached is not None:
            return self._wrap(chunk, context=cached)

        prompt = build_enrichment_prompt(section_path=chunk.section_path, chunk_text=chunk.text)
        raw = self._llm.generate(prompt)
        context = _clean(raw)
        if not context:
            raise ValueError(f"empty enrichment response for {chunk.chunk_id}")
        self._cache[key] = context
        self._save_cache()
        return self._wrap(chunk, context=context)

    def enrich_batch(self, chunks: list[Chunk]) -> list[EnrichedChunk]:
        return [self.enrich(c) for c in chunks]

    @staticmethod
    def _wrap(chunk: Chunk, *, context: str) -> EnrichedChunk:
        text = f"{context}\n\n{chunk.text}" if context else chunk.text
        return EnrichedChunk(
            chunk_id=chunk.chunk_id,
            party=chunk.party,
            text=text,
            section_path=chunk.section_path,
            page=chunk.page,
            chunk_idx=chunk.chunk_idx,
            context=context,
        )
