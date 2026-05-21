"""End-to-end ingestion pipeline.

Manifestos:   PDF -> blocks -> headings -> chunks -> enriched -> embedded
              -> ChromaDB (``klartext_manifestos``) + BM25 pickle.
Tweets:       JSON -> embedded -> ChromaDB (``klartext_tweets``).

The orchestration functions take the LLM, embedder, and collection as
arguments so they can be exercised in unit tests with fakes. ``main()``
wires up the real Ollama + BGE-M3 + ChromaDB stack and is what
``uv run python scripts/ingest.py`` calls.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import structlog

from backend.bm25_index import Bm25Index
from backend.chunker import Chunk, chunk_document
from backend.enricher import ContextEnricher, EnrichedChunk
from backend.pdf_parser import classify_blocks, detect_heading_sizes, parse_pdf

log = structlog.get_logger(__name__)


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class ChromaCollection(Protocol):
    def add(
        self,
        *,
        ids: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        metadatas: Sequence[dict],
        documents: Sequence[str],
    ) -> None: ...


@dataclass(frozen=True)
class IngestReport:
    parties: list[str]
    chunks_total: int
    bm25_path: Path | None


def party_from_pdf_path(path: Path) -> str:
    return Path(path).stem.lower()


def process_pdf(
    path: Path,
    *,
    party: str | None = None,
    chunk_size: int = 500,
    overlap: int = 100,
) -> list[Chunk]:
    party = party or party_from_pdf_path(path)
    doc = parse_pdf(path, party=party)
    if not doc.blocks:
        return []
    sizes = detect_heading_sizes(doc.blocks)
    classified = classify_blocks(doc.blocks, sizes)
    return chunk_document(party=party, blocks=classified, chunk_size=chunk_size, overlap=overlap)


def _metadata(chunk: EnrichedChunk, source_pdf: Path | str) -> dict:
    return {
        "party": chunk.party,
        "section_path": chunk.section_path,
        "page": chunk.page,
        "chunk_id": chunk.chunk_id,
        "context": chunk.context,
        "source_pdf": str(source_pdf),
    }


def ingest_manifestos(
    *,
    manifestos_dir: Path,
    enricher: ContextEnricher,
    embedder: Embedder,
    collection: ChromaCollection,
    bm25_path: Path,
    chunk_size: int = 500,
    overlap: int = 100,
) -> IngestReport:
    manifestos_dir = Path(manifestos_dir)
    pdfs = sorted(manifestos_dir.glob("*.pdf"))
    parties: list[str] = []
    all_enriched: list[EnrichedChunk] = []
    source_by_id: dict[str, Path] = {}

    for pdf in pdfs:
        party = party_from_pdf_path(pdf)
        parties.append(party)
        chunks = process_pdf(pdf, party=party, chunk_size=chunk_size, overlap=overlap)
        enriched = enricher.enrich_batch(chunks)
        all_enriched.extend(enriched)
        for e in enriched:
            source_by_id[e.chunk_id] = pdf
        log.info("ingest.pdf.processed", party=party, chunks=len(chunks))

    if not all_enriched:
        log.warning("ingest.no_chunks", dir=str(manifestos_dir))
        return IngestReport(parties=parties, chunks_total=0, bm25_path=None)

    texts = [e.text for e in all_enriched]
    embeddings = embedder.embed(texts)
    collection.add(
        ids=[e.chunk_id for e in all_enriched],
        embeddings=embeddings,
        metadatas=[_metadata(e, source_by_id[e.chunk_id]) for e in all_enriched],
        documents=texts,
    )

    bm25 = Bm25Index.build({e.chunk_id: e.text for e in all_enriched})
    bm25.save(bm25_path)
    log.info(
        "ingest.manifestos.complete",
        chunks=len(all_enriched),
        parties=parties,
        bm25=str(bm25_path),
    )

    return IngestReport(parties=parties, chunks_total=len(all_enriched), bm25_path=bm25_path)


def ingest_tweets(
    *,
    tweets_dir: Path,
    embedder: Embedder,
    collection: ChromaCollection,
) -> int:
    tweets_dir = Path(tweets_dir)
    items: list[tuple[str, str, dict]] = []
    for path in sorted(tweets_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        politician = data["politician"]
        for idx, tweet in enumerate(data.get("tweets", [])):
            tweet_id = f"{politician}_{idx}"
            text = tweet["text"]
            meta = {
                "politician": politician,
                "party": data.get("party", ""),
                "name": data.get("name", ""),
                "topic": tweet.get("topic", ""),
                "date": tweet.get("date", ""),
                "source_url": tweet.get("source_url", ""),
            }
            items.append((tweet_id, text, meta))

    if not items:
        return 0

    embeddings = embedder.embed([t for _, t, _ in items])
    collection.add(
        ids=[i for i, _, _ in items],
        embeddings=embeddings,
        metadatas=[m for _, _, m in items],
        documents=[t for _, t, _ in items],
    )
    log.info("ingest.tweets.complete", count=len(items))
    return len(items)


def main() -> None:
    """CLI entry. Wires up real Ollama, BGE-M3, ChromaDB from env."""
    import os

    import ollama as ollama_lib
    from dotenv import load_dotenv
    from FlagEmbedding import BGEM3FlagModel

    import chromadb

    load_dotenv()
    project_root = Path(__file__).resolve().parent.parent
    manifestos_dir = project_root / "data" / "manifestos"
    tweets_dir = project_root / "data" / "tweets"
    chromadb_path = Path(os.getenv("CHROMADB_PATH", str(project_root / "chromadb")))
    bm25_path = chromadb_path / "bm25_index.pkl"

    ollama_client = ollama_lib.Client(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))
    helper_model = os.getenv("OLLAMA_MODEL_HELPER", "qwen3:4b")

    class OllamaLLM:
        def generate(self, prompt: str) -> str:
            res = ollama_client.generate(model=helper_model, prompt=prompt, stream=False)
            return res["response"]

    class BgeEmbedder:
        def __init__(self) -> None:
            self.model = BGEM3FlagModel(
                os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
                use_fp16=False,
                device=os.getenv("EMBEDDING_DEVICE", "mps"),
            )

        def embed(self, texts: Sequence[str]) -> list[list[float]]:
            out = self.model.encode(
                list(texts),
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
            return out["dense_vecs"].tolist()

    enrichment_enabled = os.getenv("CONTEXTUAL_ENRICHMENT_ENABLED", "true").lower() == "true"
    enricher = ContextEnricher(
        llm=OllamaLLM(),
        cache_path=chromadb_path / "enrichment_cache.json",
        enabled=enrichment_enabled,
    )

    chroma_client = chromadb.PersistentClient(path=str(chromadb_path))
    manifestos_coll = chroma_client.get_or_create_collection("klartext_manifestos")
    tweets_coll = chroma_client.get_or_create_collection("klartext_tweets")

    embedder = BgeEmbedder()
    log.info("ingest.start", manifestos_dir=str(manifestos_dir))

    report = ingest_manifestos(
        manifestos_dir=manifestos_dir,
        enricher=enricher,
        embedder=embedder,
        collection=manifestos_coll,
        bm25_path=bm25_path,
    )
    log.info("ingest.manifestos.done", chunks=report.chunks_total)

    n_tweets = ingest_tweets(tweets_dir=tweets_dir, embedder=embedder, collection=tweets_coll)
    log.info("ingest.tweets.done", count=n_tweets)


if __name__ == "__main__":
    main()
