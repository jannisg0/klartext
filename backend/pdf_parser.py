"""Layout-aware PDF parsing.

Extracts text blocks together with their fontsize and page number using
PyMuPDF, then provides helpers to detect the document's heading sizes
(top-3 font sizes used as H1/H2/H3) and to classify each block accordingly.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass(frozen=True)
class TextBlock:
    text: str
    fontsize: float
    page: int
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class ClassifiedBlock:
    """A TextBlock plus its heading classification (0 = body, 1/2/3 = H1/H2/H3)."""

    text: str
    fontsize: float
    page: int
    bbox: tuple[float, float, float, float]
    heading_level: int


@dataclass(frozen=True)
class ParsedDocument:
    party: str
    blocks: list[TextBlock]
    source_pdf: Path


def parse_pdf(path: Path, party: str) -> ParsedDocument:
    """Parse a PDF into one TextBlock per line, keeping fontsize + page."""
    path = Path(path)
    blocks: list[TextBlock] = []
    with pymupdf.open(path) as doc:
        for page_index, page in enumerate(doc, start=1):
            raw = page.get_text("dict")
            for block in raw.get("blocks", []):
                if block.get("type", 0) != 0:
                    continue
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue
                    text = "".join(span.get("text", "") for span in spans).strip()
                    if not text:
                        continue
                    fontsize = max(span.get("size", 0.0) for span in spans)
                    bbox = tuple(line.get("bbox", (0.0, 0.0, 0.0, 0.0)))
                    blocks.append(
                        TextBlock(
                            text=text,
                            fontsize=round(float(fontsize), 2),
                            page=page_index,
                            bbox=bbox,
                        )
                    )
    return ParsedDocument(party=party, blocks=blocks, source_pdf=path)


def detect_heading_sizes(
    blocks: list[TextBlock],
    *,
    tolerance: float = 0.5,
) -> tuple[float, float, float]:
    """Return the three largest distinct fontsizes (descending).

    Sizes within ``tolerance`` of each other are treated as the same bucket so
    that minor anti-aliasing noise from PDFs doesn't create spurious levels.
    If fewer than three distinct sizes exist, the smallest size is repeated.
    """
    if not blocks:
        return (0.0, 0.0, 0.0)

    counts: Counter[float] = Counter(b.fontsize for b in blocks)
    sorted_sizes = sorted(counts.keys(), reverse=True)

    buckets: list[float] = []
    for size in sorted_sizes:
        if any(abs(size - existing) <= tolerance for existing in buckets):
            continue
        buckets.append(size)
        if len(buckets) == 3:
            break

    while len(buckets) < 3:
        buckets.append(buckets[-1])

    return (buckets[0], buckets[1], buckets[2])


def classify_blocks(
    blocks: list[TextBlock],
    heading_sizes: tuple[float, float, float],
    *,
    tolerance: float = 0.5,
) -> list[ClassifiedBlock]:
    """Tag each block with heading_level 1/2/3 or 0 for body text.

    A block is considered a heading only if its fontsize is within ``tolerance``
    of one of the heading-size buckets AND its size is strictly above the body
    size (heading_sizes[2]) so that 'body' text isn't mislabeled as H3.
    """
    h1, h2, h3 = heading_sizes
    body_size = min(b.fontsize for b in blocks) if blocks else 0.0
    classified: list[ClassifiedBlock] = []
    for block in blocks:
        level = 0
        if abs(block.fontsize - h1) <= tolerance and block.fontsize > body_size:
            level = 1
        elif abs(block.fontsize - h2) <= tolerance and block.fontsize > body_size:
            level = 2
        elif abs(block.fontsize - h3) <= tolerance and block.fontsize > body_size:
            level = 3
        classified.append(
            ClassifiedBlock(
                text=block.text,
                fontsize=block.fontsize,
                page=block.page,
                bbox=block.bbox,
                heading_level=level,
            )
        )
    return classified
