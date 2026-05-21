"""Integration tests for the ingest orchestrator.

PyMuPDF and the parser/chunker/enricher modules run for real. The LLM,
embedder, and ChromaDB collection are faked so the tests are fast and
deterministic.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from scripts.ingest import ingest_manifestos, ingest_tweets, party_from_pdf_path
from tests.conftest import PdfLine, build_pdf


class _FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        return f"Kontext-{self.calls}."


class _FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        batch = list(texts)
        self.calls.append(batch)
        return [[float(len(t) % 17), float(len(t) % 13), float(len(t) % 7)] for t in batch]


@dataclass
class _FakeCollection:
    ids: list[str] = field(default_factory=list)
    embeddings: list[list[float]] = field(default_factory=list)
    metadatas: list[dict] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)

    def add(self, *, ids, embeddings, metadatas, documents) -> None:
        self.ids.extend(ids)
        self.embeddings.extend(embeddings)
        self.metadatas.extend(metadatas)
        self.documents.extend(documents)


def _two_party_pdfs(dir_: Path) -> None:
    build_pdf(
        dir_ / "spd.pdf",
        [
            PdfLine("Wirtschaft", 18),
            PdfLine("Steuerpolitik", 14),
            PdfLine("Wir wollen eine Vermoegensteuer einfuehren.", 10),
        ],
    )
    build_pdf(
        dir_ / "cdu.pdf",
        [
            PdfLine("Wirtschaft", 18),
            PdfLine("Steuern", 14),
            PdfLine("Wir senken die Steuern fuer kleine Einkommen.", 10),
        ],
    )


def test_party_from_pdf_path_uses_stem_lowercased():
    assert party_from_pdf_path(Path("/x/SPD.PDF")) == "spd"
    assert party_from_pdf_path(Path("cdu.pdf")) == "cdu"


def test_ingest_manifestos_empty_dir_produces_empty_report(tmp_path: Path):
    manifestos = tmp_path / "manifestos"
    manifestos.mkdir()
    from backend.enricher import ContextEnricher

    report = ingest_manifestos(
        manifestos_dir=manifestos,
        enricher=ContextEnricher(llm=_FakeLLM(), cache_path=tmp_path / "cache.json", enabled=False),
        embedder=_FakeEmbedder(),
        collection=_FakeCollection(),
        bm25_path=tmp_path / "bm25.pkl",
    )

    assert report.chunks_total == 0
    assert report.parties == []
    assert not (tmp_path / "bm25.pkl").exists()


def test_ingest_manifestos_indexes_two_pdfs(tmp_path: Path):
    manifestos = tmp_path / "manifestos"
    manifestos.mkdir()
    _two_party_pdfs(manifestos)

    from backend.enricher import ContextEnricher

    llm = _FakeLLM()
    embedder = _FakeEmbedder()
    collection = _FakeCollection()
    bm25_path = tmp_path / "bm25.pkl"

    report = ingest_manifestos(
        manifestos_dir=manifestos,
        enricher=ContextEnricher(llm=llm, cache_path=tmp_path / "cache.json", enabled=True),
        embedder=embedder,
        collection=collection,
        bm25_path=bm25_path,
    )

    assert report.chunks_total >= 2
    assert set(report.parties) == {"spd", "cdu"}
    assert bm25_path.exists()

    # Each id matches expected schema and is unique.
    assert len(set(collection.ids)) == len(collection.ids)
    for cid in collection.ids:
        assert cid.startswith(("spd_", "cdu_"))

    # Documents passed to embedder include the enrichment context.
    for doc in collection.documents:
        assert "Kontext-" in doc

    # Metadata carries the required fields per CLAUDE.md.
    for meta in collection.metadatas:
        assert {"party", "section_path", "page", "chunk_id", "context"} <= meta.keys()


def test_ingest_manifestos_reuses_enrichment_cache(tmp_path: Path):
    manifestos = tmp_path / "manifestos"
    manifestos.mkdir()
    _two_party_pdfs(manifestos)
    cache = tmp_path / "cache.json"

    from backend.enricher import ContextEnricher

    llm1 = _FakeLLM()
    ingest_manifestos(
        manifestos_dir=manifestos,
        enricher=ContextEnricher(llm=llm1, cache_path=cache, enabled=True),
        embedder=_FakeEmbedder(),
        collection=_FakeCollection(),
        bm25_path=tmp_path / "bm25.pkl",
    )
    first_calls = llm1.calls

    llm2 = _FakeLLM()
    ingest_manifestos(
        manifestos_dir=manifestos,
        enricher=ContextEnricher(llm=llm2, cache_path=cache, enabled=True),
        embedder=_FakeEmbedder(),
        collection=_FakeCollection(),
        bm25_path=tmp_path / "bm25.pkl",
    )

    assert first_calls > 0
    assert llm2.calls == 0


def test_ingest_tweets_indexes_each_tweet_with_stable_id(tmp_path: Path):
    tweets_dir = tmp_path / "tweets"
    tweets_dir.mkdir()
    payload = {
        "politician": "annalena_baerbock",
        "name": "Annalena Baerbock",
        "party": "gruene",
        "tweets": [
            {"text": "Klima ist Sicherheit.", "date": "2024-03-12", "topic": "klima"},
            {"text": "Diplomatie statt Eskalation.", "date": "2024-04-01", "topic": "aussen"},
        ],
    }
    (tweets_dir / "annalena_baerbock.json").write_text(json.dumps(payload), encoding="utf-8")
    (tweets_dir / "_example.json").write_text(json.dumps(payload), encoding="utf-8")

    embedder = _FakeEmbedder()
    collection = _FakeCollection()

    n = ingest_tweets(tweets_dir=tweets_dir, embedder=embedder, collection=collection)

    assert n == 2
    assert collection.ids == ["annalena_baerbock_0", "annalena_baerbock_1"]
    assert collection.metadatas[0]["party"] == "gruene"
    assert collection.metadatas[0]["politician"] == "annalena_baerbock"
