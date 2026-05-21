"""Post-hoc citation verification.

After the LLM produces an answer, every ``[PARTEI – Seite X]`` marker
in the output is matched against the metadata of the retrieved
chunks. Markers that don't correspond to a real (party, page) pair
from the retrieval set are surfaced as ``unverified`` so the API can
warn the user (and we can log faithfulness drift over time).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from backend.retriever import Hit

# en-dash, em-dash, or ASCII hyphen separator, with optional spaces.
CITATION_RE = re.compile(r"\[\s*(?P<party>\w+)\s*[–—-]\s*Seite\s+(?P<page>\d+)\s*\]")


@dataclass(frozen=True)
class Citation:
    party: str
    page: int
    raw: str


@dataclass(frozen=True)
class VerificationResult:
    verified: list[Citation]
    unverified: list[Citation]


def extract_citations(text: str) -> list[Citation]:
    out: list[Citation] = []
    for match in CITATION_RE.finditer(text):
        out.append(
            Citation(
                party=match.group("party").lower(),
                page=int(match.group("page")),
                raw=match.group(0),
            )
        )
    return out


def verify_citations(answer: str, hits: Sequence[Hit]) -> VerificationResult:
    known: set[tuple[str, int]] = {
        (str(h.metadata.get("party", "")).lower(), int(h.metadata.get("page", -1))) for h in hits
    }
    citations = extract_citations(answer)

    seen: set[tuple[str, int]] = set()
    verified: list[Citation] = []
    unverified: list[Citation] = []
    for c in citations:
        key = (c.party, c.page)
        if key in seen:
            continue
        seen.add(key)
        if key in known:
            verified.append(c)
        else:
            unverified.append(c)

    return VerificationResult(verified=verified, unverified=unverified)
