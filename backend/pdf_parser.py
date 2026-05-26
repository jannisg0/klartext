"""Markdown-aware PDF parsing via pymupdf4llm.

Converts each PDF page to Markdown, preserving heading hierarchy,
bullet lists, and table structure. Downstream chunking operates on
the structured Markdown rather than on raw text blocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf4llm


@dataclass(frozen=True)
class MarkdownPage:
    text: str
    page: int


@dataclass(frozen=True)
class MarkdownDocument:
    party: str
    pages: list[MarkdownPage]
    source_pdf: Path


def parse_pdf(path: Path | str, party: str) -> MarkdownDocument:
    """Parse a PDF into per-page Markdown chunks.

    Uses pymupdf4llm which preserves heading levels (via fontsize heuristics),
    bullet lists, and table structures — no manual fontsize classification needed.
    Page numbers are 1-based.
    """
    path = Path(path)
    raw_chunks = pymupdf4llm.to_markdown(str(path), page_chunks=True)
    pages: list[MarkdownPage] = []
    for chunk in raw_chunks:
        text = chunk.get("text", "")
        if not text.strip():
            continue
        # pymupdf4llm returns 1-based page number in metadata["page_number"]
        page_num = chunk.get("metadata", {}).get("page_number", 1)
        pages.append(MarkdownPage(text=text, page=page_num))
    return MarkdownDocument(party=party, pages=pages, source_pdf=path)
