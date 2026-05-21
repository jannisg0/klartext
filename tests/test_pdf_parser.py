"""Tests for the layout-aware PDF parser."""

from __future__ import annotations

import pytest

from backend.pdf_parser import (
    classify_blocks,
    detect_heading_sizes,
    parse_pdf,
)
from tests.conftest import PdfLine


def test_parse_pdf_returns_blocks_with_text_and_fontsize(simple_pdf):
    doc = parse_pdf(simple_pdf, party="spd")

    assert doc.party == "spd"
    texts = [b.text for b in doc.blocks]
    assert "Wirtschaft" in texts
    assert "Steuerpolitik" in texts
    assert any("Vermoegensteuer" in t for t in texts)

    sizes_for_wirtschaft = [b.fontsize for b in doc.blocks if b.text == "Wirtschaft"]
    assert sizes_for_wirtschaft == [pytest.approx(18, abs=0.5)]
    sizes_for_steuer = [b.fontsize for b in doc.blocks if b.text == "Steuerpolitik"]
    assert sizes_for_steuer == [pytest.approx(14, abs=0.5)]

    for block in doc.blocks:
        assert block.page >= 1
        assert block.fontsize > 0
        assert block.text.strip() == block.text


def test_parse_pdf_preserves_page_numbers(make_pdf):
    lines = [
        PdfLine("first page line", 10, page_break_after=True),
        PdfLine("second page line", 10),
    ]
    pdf = make_pdf("twopage.pdf", lines)

    doc = parse_pdf(pdf, party="cdu")

    by_text = {b.text: b.page for b in doc.blocks}
    assert by_text["first page line"] == 1
    assert by_text["second page line"] == 2


def test_detect_heading_sizes_returns_top_three_descending(simple_pdf):
    doc = parse_pdf(simple_pdf, party="spd")

    h1, h2, h3 = detect_heading_sizes(doc.blocks)

    assert h1 > h2 > h3
    assert h1 == pytest.approx(18, abs=0.5)
    assert h2 == pytest.approx(14, abs=0.5)
    assert h3 == pytest.approx(10, abs=0.5)


def test_detect_heading_sizes_with_only_one_size(make_pdf):
    """Documents without headings still yield three sizes (degenerate but defined)."""
    pdf = make_pdf("flat.pdf", [PdfLine(f"line {i}", 10) for i in range(5)])
    doc = parse_pdf(pdf, party="fdp")

    sizes = detect_heading_sizes(doc.blocks)

    assert len(sizes) == 3
    assert sizes[0] >= sizes[1] >= sizes[2]


def test_classify_blocks_labels_heading_levels(simple_pdf):
    doc = parse_pdf(simple_pdf, party="spd")
    sizes = detect_heading_sizes(doc.blocks)

    classified = classify_blocks(doc.blocks, sizes)

    by_text = {c.text: c for c in classified if c.text in {"Wirtschaft", "Steuerpolitik"}}
    assert by_text["Wirtschaft"].heading_level == 1
    assert by_text["Steuerpolitik"].heading_level == 2

    body_blocks = [c for c in classified if c.heading_level == 0]
    assert any("Vermoegensteuer" in c.text for c in body_blocks)
