"""Tests for the Markdown-aware chunker.

The chunker must:
- emit chunks with deterministic IDs ``{party}_p{page}_c{idx}``
- carry ``section_path`` derived from Markdown heading hierarchy
- NEVER merge text across section boundaries
- respect chunk_size + overlap inside a single section
- never split inside a Markdown table block
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.chunker import chunk_document
from backend.pdf_parser import MarkdownDocument, MarkdownPage


def _doc(markdown: str, party: str = "spd", page: int = 1) -> MarkdownDocument:
    return MarkdownDocument(
        party=party,
        pages=[MarkdownPage(text=markdown, page=page)],
        source_pdf=Path("dummy.pdf"),
    )


def _multipage_doc(pages: list[tuple[str, int]], party: str = "spd") -> MarkdownDocument:
    return MarkdownDocument(
        party=party,
        pages=[MarkdownPage(text=text, page=p) for text, p in pages],
        source_pdf=Path("dummy.pdf"),
    )


# ─── basic behaviour ────────────────────────────────────────────────────────


def test_chunker_returns_chunks_with_required_metadata():
    doc = _doc(
        "# Wirtschaft\n\n## Steuerpolitik\n\nVermoegensteuer wird wieder eingefuehrt.",
        party="spd",
        page=3,
    )
    chunks = chunk_document(doc)

    assert len(chunks) == 1
    c = chunks[0]
    assert c.party == "spd"
    assert c.section_path == "Wirtschaft > Steuerpolitik"
    assert "Vermoegensteuer" in c.text
    assert c.page == 3
    assert c.chunk_id == "spd_p3_c0"


def test_chunker_never_crosses_section_boundaries():
    doc = _doc(
        "# Wirtschaft\n\n"
        "## Steuerpolitik\n\n"
        "Wir wollen die Vermoegensteuer.\n\n"
        "## Arbeitsmarkt\n\n"
        "Mindestlohn auf 15 Euro."
    )
    chunks = chunk_document(doc)

    paths = {c.section_path for c in chunks}
    assert paths == {"Wirtschaft > Steuerpolitik", "Wirtschaft > Arbeitsmarkt"}
    for c in chunks:
        if "Vermoegen" in c.text:
            assert "Mindestlohn" not in c.text
        if "Mindestlohn" in c.text:
            assert "Vermoegen" not in c.text


def test_chunker_splits_long_section_with_overlap():
    words = [f"wort{i}" for i in range(120)]
    body = " ".join(words)
    doc = _doc(f"# Wirtschaft\n\n## Steuerpolitik\n\n{body}")

    chunks = chunk_document(doc, chunk_size=50, overlap=10)

    assert len(chunks) >= 3
    ids = [c.chunk_id for c in chunks]
    assert ids == [f"spd_p1_c{i}" for i in range(len(chunks))]

    first_tail = chunks[0].text.split()[-10:]
    second_head = chunks[1].text.split()[:10]
    assert first_tail == second_head

    for c in chunks:
        assert len(c.text.split()) <= 50


def test_chunker_skips_empty_sections():
    doc = _doc(
        "# Wirtschaft\n\n" "## Steuerpolitik\n\n" "## Arbeitsmarkt\n\n" "Mindestlohn auf 15 Euro.",
        page=4,
    )
    chunks = chunk_document(doc)

    assert len(chunks) == 1
    assert chunks[0].section_path == "Wirtschaft > Arbeitsmarkt"


def test_chunker_uses_first_page_of_section():
    doc = _multipage_doc(
        [
            ("# Wirtschaft\n\nBody line one.", 5),
            ("Body line two.", 6),
        ]
    )
    chunks = chunk_document(doc)

    assert len(chunks) == 1
    assert chunks[0].page == 5


def test_chunker_rejects_invalid_overlap():
    doc = _doc("# H\n\nbody")
    with pytest.raises(ValueError):
        chunk_document(doc, chunk_size=50, overlap=50)


# ─── ID schema ──────────────────────────────────────────────────────────────


def test_chunker_ids_are_deterministic():
    doc = _doc("# H\n\n" + " ".join(f"w{i}" for i in range(200)))
    chunks1 = chunk_document(doc, chunk_size=50, overlap=10)
    chunks2 = chunk_document(doc, chunk_size=50, overlap=10)

    assert [c.chunk_id for c in chunks1] == [c.chunk_id for c in chunks2]


def test_chunker_ids_follow_page_local_counter():
    doc = _multipage_doc(
        [
            ("# Wirtschaft\n\n## Steuerpolitik\n\nBody A.\n\n## Arbeitsmarkt\n\nBody B.", 2),
            ("## Bildung\n\nBody C.", 3),
        ]
    )
    chunks = chunk_document(doc)

    page2_ids = [c.chunk_id for c in chunks if c.page == 2]
    page3_ids = [c.chunk_id for c in chunks if c.page == 3]
    assert page2_ids == ["spd_p2_c0", "spd_p2_c1"]
    assert page3_ids == ["spd_p3_c0"]


# ─── table integrity ────────────────────────────────────────────────────────


def test_chunker_does_not_split_inside_table():
    table_rows = "\n".join(f"| Partei | Position {i} |" for i in range(20))
    separator = "| --- | --- |"
    table = f"| Partei | Position |\n{separator}\n{table_rows}"
    doc = _doc(f"# Wirtschaft\n\n{table}")

    chunks = chunk_document(doc, chunk_size=20, overlap=5)

    for c in chunks:
        lines = c.text.splitlines()
        # A separator row without a preceding header row indicates a mid-table split.
        # After splitting, the first line of a chunk should never be a separator.
        if lines:
            assert not (
                lines[0].startswith("|") and "---" in lines[0]
            ), f"Chunk starts with table separator (orphaned): {lines[0]!r}"
