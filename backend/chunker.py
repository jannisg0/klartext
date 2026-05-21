"""Structure-aware chunking.

Walks a list of ``ClassifiedBlock``s and groups them into leaf sections
(deepest open heading path at any point). Body text of each section is
then split into chunks of approximately ``chunk_size`` tokens with
``overlap`` tokens shared between consecutive chunks. Chunks never span
section boundaries, even when the section is short or empty.

The tokenizer is injected so tests can use a deterministic
whitespace-based tokenizer; production callers can plug in tiktoken,
the BGE-M3 tokenizer, or anything that returns a list-like of tokens.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from backend.pdf_parser import ClassifiedBlock


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    party: str
    text: str
    section_path: str
    page: int
    chunk_idx: int


@dataclass
class _Section:
    path_parts: list[str]
    body_blocks: list[ClassifiedBlock]

    @property
    def path(self) -> str:
        return " > ".join(self.path_parts)


def _default_tokenize(text: str) -> list[str]:
    return text.split()


def _collect_sections(blocks: Sequence[ClassifiedBlock]) -> list[_Section]:
    """Group blocks into leaf sections based on heading levels."""
    open_path: list[str] = []
    sections: list[_Section] = []
    current: _Section | None = None

    for block in blocks:
        if block.heading_level > 0:
            level = block.heading_level
            open_path = open_path[: level - 1]
            open_path.append(block.text)
            current = _Section(path_parts=list(open_path), body_blocks=[])
            sections.append(current)
        else:
            if current is None:
                continue  # body text before any heading is dropped
            current.body_blocks.append(block)

    return [s for s in sections if s.body_blocks]


def chunk_document(
    *,
    party: str,
    blocks: Sequence[ClassifiedBlock],
    chunk_size: int = 500,
    overlap: int = 100,
    tokenize: Callable[[str], Sequence[str]] | None = None,
) -> list[Chunk]:
    """Split ``blocks`` into section-bounded, overlapping chunks."""
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be in [0, chunk_size)")
    tok = tokenize or _default_tokenize

    chunks: list[Chunk] = []
    chunk_counter_by_page: dict[int, int] = {}

    for section in _collect_sections(blocks):
        body_text = " ".join(b.text for b in section.body_blocks).strip()
        if not body_text:
            continue
        page = section.body_blocks[0].page
        tokens = list(tok(body_text))
        if not tokens:
            continue

        step = chunk_size - overlap
        start = 0
        while start < len(tokens):
            window = tokens[start : start + chunk_size]
            text = " ".join(window)
            idx = chunk_counter_by_page.get(page, 0)
            chunk_counter_by_page[page] = idx + 1
            chunks.append(
                Chunk(
                    chunk_id=f"{party}_p{page}_c{idx}",
                    party=party,
                    text=text,
                    section_path=section.path,
                    page=page,
                    chunk_idx=idx,
                )
            )
            if start + chunk_size >= len(tokens):
                break
            start += step

    return chunks
