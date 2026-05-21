"""Sparse BM25 index over chunk corpus.

Wraps ``rank_bm25.BM25Okapi`` with a stable id->doc mapping and pickle
persistence to ``chromadb/bm25_index.pkl`` (path is chosen by the
caller). Tokenization is a lightweight Unicode-aware lowercase split
that's identical at build and query time so scores stay reproducible.
"""

from __future__ import annotations

import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path

from rank_bm25 import BM25Okapi

_TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)


def tokenize_for_bm25(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class Bm25Index:
    chunk_ids: list[str]
    bm25: BM25Okapi = field(repr=False)

    @classmethod
    def build(cls, docs: dict[str, str]) -> Bm25Index:
        if not docs:
            raise ValueError("BM25 corpus must not be empty")
        chunk_ids = list(docs.keys())
        tokenized = [tokenize_for_bm25(docs[cid]) for cid in chunk_ids]
        return cls(chunk_ids=chunk_ids, bm25=BM25Okapi(tokenized))

    def search(self, query: str, *, top_k: int) -> list[tuple[str, float]]:
        scores = self.bm25.get_scores(tokenize_for_bm25(query))
        ranked = sorted(
            zip(self.chunk_ids, scores, strict=True),
            key=lambda x: x[1],
            reverse=True,
        )
        return [(cid, float(score)) for cid, score in ranked[:top_k]]

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump({"chunk_ids": self.chunk_ids, "bm25": self.bm25}, f)

    @classmethod
    def load(cls, path: Path) -> Bm25Index:
        with Path(path).open("rb") as f:
            data = pickle.load(f)
        return cls(chunk_ids=data["chunk_ids"], bm25=data["bm25"])
