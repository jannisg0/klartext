"""Tests for the Markdown-aware PDF parser (pymupdf4llm)."""

from __future__ import annotations

from pathlib import Path

from backend.pdf_parser import MarkdownDocument, MarkdownPage, parse_pdf
from tests.conftest import PdfLine


def test_parse_pdf_returns_markdown_document(simple_pdf):
    doc = parse_pdf(simple_pdf, party="spd")

    assert isinstance(doc, MarkdownDocument)
    assert doc.party == "spd"
    assert isinstance(doc.pages, list)
    assert len(doc.pages) >= 1
    for page in doc.pages:
        assert isinstance(page, MarkdownPage)
        assert isinstance(page.text, str)
        assert page.page >= 1


def test_parse_pdf_preserves_party(simple_pdf):
    doc = parse_pdf(simple_pdf, party="gruene")
    assert doc.party == "gruene"


def test_parse_pdf_source_pdf_recorded(simple_pdf):
    doc = parse_pdf(simple_pdf, party="spd")
    assert doc.source_pdf == Path(simple_pdf)


def test_parse_pdf_markdown_contains_body_text(simple_pdf):
    doc = parse_pdf(simple_pdf, party="spd")
    full_text = "\n".join(p.text for p in doc.pages)
    assert "Vermoegensteuer" in full_text
    assert "Mindestlohn" in full_text


def test_parse_pdf_headings_appear_in_markdown(simple_pdf):
    doc = parse_pdf(simple_pdf, party="spd")
    full_text = "\n".join(p.text for p in doc.pages)
    assert "Wirtschaft" in full_text
    assert "Steuerpolitik" in full_text


def test_parse_pdf_preserves_page_numbers(make_pdf):
    lines = [
        PdfLine("first page line", 10, page_break_after=True),
        PdfLine("second page line", 10),
    ]
    pdf = make_pdf("twopage.pdf", lines)
    doc = parse_pdf(pdf, party="cdu")

    page_numbers = [p.page for p in doc.pages]
    assert 1 in page_numbers
    assert 2 in page_numbers
    assert all(n >= 1 for n in page_numbers)


def test_parse_pdf_skips_empty_pages(make_pdf):
    lines = [PdfLine("some content", 10)]
    pdf = make_pdf("nonempty.pdf", lines)
    doc = parse_pdf(pdf, party="fdp")
    assert len(doc.pages) >= 1
    for p in doc.pages:
        assert p.text.strip()


def test_parse_pdf_accepts_path_str(simple_pdf):
    doc = parse_pdf(str(simple_pdf), party="spd")
    assert doc.party == "spd"
    assert len(doc.pages) >= 1
