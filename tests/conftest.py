"""Shared pytest fixtures.

Generates real (small) PDFs in tmp_path so the parser is tested end-to-end
against PyMuPDF rather than against a mock of PyMuPDF.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pymupdf
import pytest


@dataclass(frozen=True)
class PdfLine:
    text: str
    fontsize: float
    page_break_after: bool = False


def build_pdf(path: Path, lines: Sequence[PdfLine]) -> Path:
    """Render lines to a PDF with the given fontsizes.

    Each line is placed below the previous one. ``page_break_after=True``
    starts a fresh page after the line. PyMuPDF's default font is used.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    y = 60.0
    margin_bottom = 780.0
    for line in lines:
        if y > margin_bottom:
            page = doc.new_page()
            y = 60.0
        page.insert_text((50, y), line.text, fontsize=line.fontsize)
        y += line.fontsize * 1.6
        if line.page_break_after:
            page = doc.new_page()
            y = 60.0
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def make_pdf(tmp_path: Path):
    """Return a callable that builds a PDF in tmp_path and returns the path."""

    def _make(name: str, lines: Sequence[PdfLine]) -> Path:
        return build_pdf(tmp_path / name, lines)

    return _make


@pytest.fixture
def simple_pdf(make_pdf):
    """Minimal two-section PDF used by several tests.

    Layout:
      H1: "Wirtschaft"           (18pt)
        H2: "Steuerpolitik"      (14pt)
          body x N               (10pt)
        H2: "Arbeitsmarkt"       (14pt)
          body x N               (10pt)
    """
    lines = [
        PdfLine("Wirtschaft", 18),
        PdfLine("Steuerpolitik", 14),
        PdfLine("Wir setzen auf eine gerechte Besteuerung grosser Vermoegen.", 10),
        PdfLine("Die Vermoegensteuer soll wieder eingefuehrt werden.", 10),
        PdfLine("Arbeitsmarkt", 14),
        PdfLine("Der Mindestlohn muss auf 15 Euro pro Stunde steigen.", 10),
    ]
    return make_pdf("simple.pdf", lines)
