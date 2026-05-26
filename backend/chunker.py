"""Markdown-aware chunking.

Processes MarkdownDocument pages produced by pdf_parser. Derives section
boundaries from Markdown heading syntax (``#``, ``##``, ``###``) rather
than fontsize heuristics.  Body text of each section is split into
overlapping chunks; Markdown table blocks are treated as atomic units and
never split mid-table.

Chunk IDs follow the idempotent schema ``{party}_p{page}_c{idx}`` where
``page`` is the 1-based number of the page containing the first body line
of the section and ``idx`` is a per-page counter that increments across
all chunks on that page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.pdf_parser import MarkdownDocument

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$")
_TABLE_ROW_RE = re.compile(r"^\s*\|")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    party: str
    text: str
    section_path: str
    page: int
    chunk_idx: int


# ─── internal helpers ────────────────────────────────────────────────────────


def _section_path(open_headings: list[tuple[int, str]]) -> str:
    return " > ".join(title for _, title in open_headings)


def _table_aware_chunks(body_text: str, chunk_size: int, step: int) -> list[str]:
    """Sliding-window chunker that preserves Markdown table line structure.

    A table block is a run of consecutive lines starting with ``|``.  The
    window never splits inside a table block: it is extended forward to the
    end of the block before closing a chunk, and the next window opens after
    the block.  Chunk text uses ``\\n`` between table rows so that
    ``text.splitlines()`` returns individual table rows — callers can rely on
    the first line of a chunk not being an orphaned separator row.
    """
    lines = body_text.splitlines()
    if not lines:
        return []

    # Per-line: token list + table flag
    line_tokens: list[list[str]] = [line.split() for line in lines]
    line_is_table: list[bool] = [bool(_TABLE_ROW_RE.match(line)) for line in lines]

    # Flat token → line index mapping
    all_tokens: list[str] = []
    token_line: list[int] = []
    for li, toks in enumerate(line_tokens):
        all_tokens.extend(toks)
        token_line.extend([li] * len(toks))

    total = len(all_tokens)
    if total == 0:
        return []

    def _table_block_end(li: int) -> int:
        """Return the index of the last line in the table block containing ``li``."""
        while li + 1 < len(lines) and line_is_table[li + 1]:
            li += 1
        return li

    def _snap_end(pos: int) -> int:
        """Extend pos past any table block that pos lands inside."""
        if pos <= 0 or pos >= total:
            return min(pos, total)
        prev_li = token_line[pos - 1]
        if not line_is_table[prev_li]:
            return pos
        table_end_li = _table_block_end(prev_li)
        while pos < total and token_line[pos] <= table_end_li:
            pos += 1
        return pos

    def _snap_start(pos: int) -> int:
        """Advance pos out of any table block it lands in."""
        if pos >= total:
            return total
        li = token_line[pos]
        if not line_is_table[li]:
            return pos
        table_end_li = _table_block_end(li)
        while pos < total and token_line[pos] <= table_end_li:
            pos += 1
        return pos

    def _reconstruct(start: int, end: int) -> str:
        """Build chunk text preserving ``\\n`` between table rows."""
        if start >= end:
            return ""
        first_li = token_line[start]
        last_li = token_line[end - 1]
        parts: list[tuple[str, bool]] = []
        for li in range(first_li, last_li + 1):
            line_toks = [all_tokens[i] for i in range(start, end) if token_line[i] == li]
            if line_toks:
                parts.append((" ".join(line_toks), line_is_table[li]))
        if not parts:
            return ""
        buf = [parts[0][0]]
        for i in range(1, len(parts)):
            sep = "\n" if (parts[i - 1][1] or parts[i][1]) else " "
            buf.append(sep + parts[i][0])
        return "".join(buf)

    result: list[str] = []
    start = 0
    while start < total:
        tentative_end = min(start + chunk_size, total)
        end = _snap_end(tentative_end)
        chunk_text = _reconstruct(start, end)
        if chunk_text.strip():
            result.append(chunk_text)
        next_start = start + step
        if next_start >= total:
            break
        next_start = _snap_start(next_start)
        if next_start >= total or next_start >= end:
            break
        start = next_start

    return result


# ─── public API ──────────────────────────────────────────────────────────────


def chunk_document(
    doc: MarkdownDocument,
    *,
    chunk_size: int = 500,
    overlap: int = 100,
) -> list[Chunk]:
    """Convert a MarkdownDocument into section-bounded, overlapping Chunks."""
    if overlap >= chunk_size:
        raise ValueError(f"overlap={overlap} must be less than chunk_size={chunk_size}")

    step = chunk_size - overlap
    chunks: list[Chunk] = []
    page_counters: dict[int, int] = {}

    open_headings: list[tuple[int, str]] = []
    body_lines: list[tuple[str, int]] = []

    def _flush() -> None:
        if not body_lines:
            return
        first_page = body_lines[0][1]
        body_text = "\n".join(line for line, _ in body_lines).strip()
        if not body_text:
            body_lines.clear()
            return
        path = _section_path(open_headings)
        for chunk_text in _table_aware_chunks(body_text, chunk_size, step):
            idx = page_counters.get(first_page, 0)
            page_counters[first_page] = idx + 1
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.party}_p{first_page}_c{idx}",
                    party=doc.party,
                    text=chunk_text,
                    section_path=path,
                    page=first_page,
                    chunk_idx=idx,
                )
            )
        body_lines.clear()

    for md_page in doc.pages:
        for line in md_page.text.splitlines():
            match = _HEADING_RE.match(line)
            if match:
                _flush()
                level = len(match.group(1))
                title = match.group(2).strip()
                open_headings = [(lvl, t) for lvl, t in open_headings if lvl < level]
                open_headings.append((level, title))
            else:
                if not body_lines and not line.strip():
                    continue
                body_lines.append((line, md_page.page))

    _flush()
    return chunks
