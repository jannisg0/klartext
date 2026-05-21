"""Tests for post-hoc citation verification."""

from __future__ import annotations

from backend.citation_verifier import (
    Citation,
    extract_citations,
    verify_citations,
)
from backend.retriever import Hit


def _hit(party: str, page: int, text: str = "body") -> Hit:
    return Hit(
        chunk_id=f"{party}_p{page}_c0",
        score=1.0,
        text=text,
        metadata={"party": party, "page": page, "section_path": "S > X"},
    )


def test_extract_citations_finds_en_dash_form():
    text = "Die SPD will X [SPD – Seite 12]. Die CDU dagegen Y [CDU – Seite 5]."

    citations = extract_citations(text)

    assert citations == [
        Citation(party="spd", page=12, raw="[SPD – Seite 12]"),
        Citation(party="cdu", page=5, raw="[CDU – Seite 5]"),
    ]


def test_extract_citations_finds_hyphen_form():
    text = "[spd - Seite 1]"
    citations = extract_citations(text)
    assert citations[0].party == "spd"
    assert citations[0].page == 1


def test_extract_citations_returns_empty_when_none_present():
    assert extract_citations("Plain text without citations.") == []


def test_extract_citations_lowercases_party():
    citations = extract_citations("[SpD – Seite 3]")
    assert citations[0].party == "spd"


def test_verify_marks_matching_citations_as_verified():
    answer = "Aussage A [SPD – Seite 12] und B [CDU – Seite 5]."
    hits = [_hit("spd", 12), _hit("cdu", 5)]

    result = verify_citations(answer, hits)

    assert len(result.verified) == 2
    assert result.unverified == []


def test_verify_marks_party_mismatch_as_unverified():
    answer = "[FDP – Seite 1]"
    hits = [_hit("spd", 1)]

    result = verify_citations(answer, hits)

    assert result.verified == []
    assert result.unverified[0].party == "fdp"


def test_verify_marks_page_mismatch_as_unverified():
    answer = "[SPD – Seite 99]"
    hits = [_hit("spd", 12)]

    result = verify_citations(answer, hits)

    assert result.verified == []
    assert result.unverified[0].page == 99


def test_verify_deduplicates_repeated_citations():
    """Citing the same source twice in the answer should not double-count."""
    answer = "[SPD – Seite 12] und nochmal [SPD – Seite 12]."
    hits = [_hit("spd", 12)]

    result = verify_citations(answer, hits)

    assert len(result.verified) == 1
    assert result.unverified == []


def test_verify_empty_answer_yields_empty_lists():
    result = verify_citations("", [_hit("spd", 1)])
    assert result.verified == [] and result.unverified == []
