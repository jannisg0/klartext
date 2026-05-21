"""Tests for the structure-aware chunker.

The chunker must:
- emit chunks with deterministic IDs ``{party}_p{page}_c{idx}``
- carry ``section_path`` metadata such as "Wirtschaft > Steuerpolitik"
- NEVER merge text across section boundaries (even if a section is short)
- respect chunk_size + overlap inside a single section
"""

from __future__ import annotations

import pytest

from backend.chunker import chunk_document
from backend.pdf_parser import ClassifiedBlock


def _block(text: str, level: int, page: int = 1, fontsize: float = 10.0) -> ClassifiedBlock:
    return ClassifiedBlock(
        text=text, fontsize=fontsize, page=page, bbox=(0, 0, 0, 0), heading_level=level
    )


def _whitespace_tokens(text: str) -> list[str]:
    return text.split()


def test_chunker_returns_chunks_with_required_metadata():
    blocks = [
        _block("Wirtschaft", 1),
        _block("Steuerpolitik", 2),
        _block("Vermoegensteuer wird wieder eingefuehrt.", 0, page=3),
    ]

    chunks = chunk_document(
        party="spd", blocks=blocks, chunk_size=50, overlap=10, tokenize=_whitespace_tokens
    )

    assert len(chunks) == 1
    c = chunks[0]
    assert c.party == "spd"
    assert c.section_path == "Wirtschaft > Steuerpolitik"
    assert "Vermoegensteuer" in c.text
    assert c.page == 3
    assert c.chunk_id == "spd_p3_c0"


def test_chunker_never_crosses_section_boundaries():
    blocks = [
        _block("Wirtschaft", 1),
        _block("Steuerpolitik", 2, page=1),
        _block("Wir wollen die Vermoegensteuer.", 0, page=1),
        _block("Arbeitsmarkt", 2, page=2),
        _block("Mindestlohn auf 15 Euro.", 0, page=2),
    ]

    chunks = chunk_document(
        party="spd", blocks=blocks, chunk_size=500, overlap=100, tokenize=_whitespace_tokens
    )

    paths = {c.section_path for c in chunks}
    assert paths == {"Wirtschaft > Steuerpolitik", "Wirtschaft > Arbeitsmarkt"}
    for c in chunks:
        if "Vermoegen" in c.text:
            assert "Mindestlohn" not in c.text
        if "Mindestlohn" in c.text:
            assert "Vermoegen" not in c.text


def test_chunker_splits_long_section_with_overlap():
    """A single section longer than chunk_size yields multiple chunks with overlap."""
    words = [f"wort{i}" for i in range(120)]
    body = " ".join(words)
    blocks = [
        _block("Wirtschaft", 1),
        _block("Steuerpolitik", 2),
        _block(body, 0),
    ]

    chunks = chunk_document(
        party="spd", blocks=blocks, chunk_size=50, overlap=10, tokenize=_whitespace_tokens
    )

    assert len(chunks) >= 3
    ids = [c.chunk_id for c in chunks]
    assert ids == [f"spd_p1_c{i}" for i in range(len(chunks))]

    first_tail = chunks[0].text.split()[-10:]
    second_head = chunks[1].text.split()[:10]
    assert first_tail == second_head

    for c in chunks:
        assert len(_whitespace_tokens(c.text)) <= 50


def test_chunker_skips_empty_sections():
    """Sections that contain only headings (no body) emit no chunks."""
    blocks = [
        _block("Wirtschaft", 1),
        _block("Steuerpolitik", 2),
        _block("Arbeitsmarkt", 2),
        _block("Mindestlohn", 0, page=4),
    ]

    chunks = chunk_document(
        party="spd", blocks=blocks, chunk_size=500, overlap=100, tokenize=_whitespace_tokens
    )

    assert len(chunks) == 1
    assert chunks[0].section_path == "Wirtschaft > Arbeitsmarkt"


def test_chunker_uses_first_page_of_section_for_metadata():
    """A chunk's page is the first page on which its source text appears."""
    blocks = [
        _block("Wirtschaft", 1, page=5),
        _block("Body line one.", 0, page=5),
        _block("Body line two.", 0, page=6),
    ]

    chunks = chunk_document(
        party="spd", blocks=blocks, chunk_size=500, overlap=100, tokenize=_whitespace_tokens
    )

    assert len(chunks) == 1
    assert chunks[0].page == 5


def test_chunker_rejects_invalid_overlap():
    with pytest.raises(ValueError):
        chunk_document(
            party="spd",
            blocks=[_block("H", 1), _block("body", 0)],
            chunk_size=50,
            overlap=50,
            tokenize=_whitespace_tokens,
        )
