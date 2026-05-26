"""End-to-end ingestion pipeline.

Manifestos:   PDF -> Markdown pages -> chunks -> enriched -> embedded
              -> ChromaDB (``klartext_manifestos``) + BM25 pickle.
Tweets:       JSON -> embedded -> ChromaDB (``klartext_tweets``).

The orchestration functions take the LLM, embedder, and collection as
arguments so they can be exercised in unit tests with fakes. ``main()``
wires up the real LLM (mlx-lm server via OpenAI SDK by default, Ollama
OpenAI gateway via ``LLM_BACKEND=ollama``) + mlx-embeddings + ChromaDB
stack and is what ``uv run python scripts/ingest.py`` calls.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from chromadb import Collection

import structlog

from backend.bm25_index import Bm25Index
from backend.chunker import Chunk, chunk_document
from backend.enricher import ContextEnricher, EnrichedChunk
from backend.pdf_parser import parse_pdf

log = structlog.get_logger(__name__)


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


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
    return chunk_document(doc, chunk_size=chunk_size, overlap=overlap)


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
    collection: Collection,
    bm25_path: Path,
    chunk_size: int = 500,
    overlap: int = 100,
) -> IngestReport:
    manifestos_dir = Path(manifestos_dir)
    pdfs = sorted(manifestos_dir.glob("*.pdf"))
    log.info("ingest.manifestos.scan", pdf_count=len(pdfs), pdfs=[p.name for p in pdfs])

    if not pdfs:
        log.warning("ingest.no_pdfs", dir=str(manifestos_dir))
        return IngestReport(parties=[], chunks_total=0, bm25_path=None)

    parties: list[str] = []
    all_enriched: list[EnrichedChunk] = []
    source_by_id: dict[str, Path] = {}

    for pdf in pdfs:
        party = party_from_pdf_path(pdf)
        parties.append(party)
        file_mb = pdf.stat().st_size / 1_048_576

        log.info("ingest.pdf.parse.start", party=party, file=pdf.name, size_mb=round(file_mb, 2))
        t0 = time.monotonic()
        doc = parse_pdf(pdf, party=party)
        parse_s = time.monotonic() - t0
        log.info(
            "ingest.pdf.parse.done",
            party=party,
            pages=len(doc.pages),
            elapsed_s=round(parse_s, 2),
        )

        chunks = chunk_document(doc, chunk_size=chunk_size, overlap=overlap)
        log.info(
            "ingest.pdf.chunk.done",
            party=party,
            chunks=len(chunks),
            chunk_size=chunk_size,
            overlap=overlap,
        )

        log.info("ingest.pdf.enrich.start", party=party, chunks=len(chunks))
        t0 = time.monotonic()
        enriched = enricher.enrich_batch(chunks)
        enrich_s = time.monotonic() - t0
        log.info(
            "ingest.pdf.enrich.done",
            party=party,
            enriched=len(enriched),
            elapsed_s=round(enrich_s, 2),
            per_chunk_s=round(enrich_s / len(enriched), 2) if enriched else 0,
        )

        all_enriched.extend(enriched)
        for e in enriched:
            source_by_id[e.chunk_id] = pdf

    if not all_enriched:
        log.warning("ingest.no_chunks", dir=str(manifestos_dir))
        return IngestReport(parties=parties, chunks_total=0, bm25_path=None)

    log.info("ingest.embed.start", total_chunks=len(all_enriched))
    t0 = time.monotonic()
    texts = [e.text for e in all_enriched]
    embeddings = embedder.embed(texts)
    embed_s = time.monotonic() - t0
    log.info(
        "ingest.embed.done",
        total_chunks=len(all_enriched),
        dims=len(embeddings[0]) if embeddings else 0,
        elapsed_s=round(embed_s, 2),
    )

    log.info("ingest.chromadb.write.start", chunks=len(all_enriched))
    t0 = time.monotonic()
    collection.add(
        ids=[e.chunk_id for e in all_enriched],
        embeddings=embeddings,
        metadatas=[_metadata(e, source_by_id[e.chunk_id]) for e in all_enriched],
        documents=texts,
    )
    log.info(
        "ingest.chromadb.write.done",
        chunks=len(all_enriched),
        elapsed_s=round(time.monotonic() - t0, 2),
    )

    log.info("ingest.bm25.build.start", chunks=len(all_enriched))
    t0 = time.monotonic()
    bm25 = Bm25Index.build({e.chunk_id: e.text for e in all_enriched})
    bm25.save(bm25_path)
    log.info(
        "ingest.bm25.build.done", path=str(bm25_path), elapsed_s=round(time.monotonic() - t0, 2)
    )

    log.info(
        "ingest.manifestos.complete",
        parties=parties,
        chunks_total=len(all_enriched),
    )
    return IngestReport(parties=parties, chunks_total=len(all_enriched), bm25_path=bm25_path)


def ingest_tweets(
    *,
    tweets_dir: Path,
    embedder: Embedder,
    collection: Collection,
) -> int:
    tweets_dir = Path(tweets_dir)
    json_files = [p for p in sorted(tweets_dir.glob("*.json")) if not p.name.startswith("_")]
    log.info("ingest.tweets.scan", file_count=len(json_files))

    items: list[tuple[str, str, dict]] = []
    for path in json_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        politician = data["politician"]
        tweet_count = len(data.get("tweets", []))
        log.info("ingest.tweets.file", politician=politician, tweets=tweet_count, file=path.name)
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
        log.info("ingest.tweets.skip", reason="no items found")
        return 0

    log.info("ingest.tweets.embed.start", total=len(items))
    t0 = time.monotonic()
    embeddings = embedder.embed([t for _, t, _ in items])
    log.info(
        "ingest.tweets.embed.done", total=len(items), elapsed_s=round(time.monotonic() - t0, 2)
    )

    collection.add(
        ids=[i for i, _, _ in items],
        embeddings=embeddings,
        metadatas=[m for _, _, m in items],
        documents=[t for _, t, _ in items],
    )
    log.info("ingest.tweets.done", count=len(items))
    return len(items)


def _build_helper_llm():
    """Build the helper LLM (mlx-lm server by default, Ollama via ``LLM_BACKEND=ollama``).

    Both backends are reached via the OpenAI SDK.  The enricher only
    needs ``generate(prompt) -> str``, which ``OpenAILLM`` satisfies.
    """
    import os

    from openai import OpenAI

    from backend.llm import GenerationConfig, OpenAILLM

    backend = os.getenv("LLM_BACKEND", "mlx").lower()
    max_tokens = int(os.getenv("MLX_MAX_TOKENS", "1024"))

    if backend == "ollama":
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        helper_model = os.getenv("OLLAMA_MODEL_HELPER", "qwen3:4b")
        client = OpenAI(base_url=ollama_host.rstrip("/") + "/v1", api_key="not-needed")
        cfg = GenerationConfig(model=helper_model, num_ctx=max_tokens)
        return OpenAILLM(completions=client.chat.completions, config=cfg)

    omlx_base_url = os.getenv("OMLX_BASE_URL", "http://localhost:8000/v1")
    omlx_model = os.getenv("OMLX_MODEL", "mlx-community/gemma-4-e4b-it-OptiQ-4bit")
    client = OpenAI(base_url=omlx_base_url, api_key="not-needed")
    cfg = GenerationConfig(model=omlx_model, num_ctx=max_tokens)
    return OpenAILLM(completions=client.chat.completions, config=cfg)


def main() -> None:
    """CLI entry. Wires up the helper LLM + mlx-embeddings + ChromaDB from env."""
    import os

    from dotenv import load_dotenv

    import chromadb

    load_dotenv()
    project_root = Path(__file__).resolve().parent.parent
    manifestos_dir = project_root / "data" / "manifestos"
    tweets_dir = project_root / "data" / "tweets"
    chromadb_path = Path(os.getenv("CHROMADB_PATH", str(project_root / "chromadb")))
    bm25_path = chromadb_path / "bm25_index.pkl"

    helper_llm = _build_helper_llm()

    from mlx_embeddings import generate as mlx_emb_generate
    from mlx_embeddings import load as mlx_emb_load

    emb_model_id = os.getenv("EMBEDDING_MODEL_MLX", "mlx-community/bge-m3-mlx-8bit")
    log.info("ingest.embedder.load.start", model=emb_model_id)
    t0 = time.monotonic()
    emb_model, emb_tokenizer = mlx_emb_load(emb_model_id)
    log.info(
        "ingest.embedder.load.done", model=emb_model_id, elapsed_s=round(time.monotonic() - t0, 2)
    )

    class BgeEmbedder:
        def embed(self, texts: Sequence[str], batch_size: int = 32) -> list[list[float]]:
            import numpy as _np

            text_list = list(texts)
            all_batches = []
            n_batches = (len(text_list) + batch_size - 1) // batch_size
            for idx, i in enumerate(range(0, len(text_list), batch_size)):
                batch = text_list[i : i + batch_size]
                log.debug(
                    "ingest.embed.batch",
                    batch=idx + 1,
                    of=n_batches,
                    size=len(batch),
                )
                out = mlx_emb_generate(emb_model, emb_tokenizer, texts=batch)
                all_batches.append(_np.array(out.text_embeds))  # type: ignore[attr-defined]
            return _np.concatenate(all_batches, axis=0).tolist()

    enrichment_enabled = os.getenv("CONTEXTUAL_ENRICHMENT_ENABLED", "true").lower() == "true"
    log.info(
        "ingest.config",
        llm_backend=os.getenv("LLM_BACKEND", "mlx"),
        enrichment=enrichment_enabled,
        chromadb_path=str(chromadb_path),
    )
    enricher = ContextEnricher(
        llm=helper_llm,
        cache_path=chromadb_path / "enrichment_cache.json",
        enabled=enrichment_enabled,
    )

    chroma_client = chromadb.PersistentClient(path=str(chromadb_path))
    manifestos_coll = chroma_client.get_or_create_collection("klartext_manifestos")
    tweets_coll = chroma_client.get_or_create_collection("klartext_tweets")

    embedder = BgeEmbedder()

    t_total = time.monotonic()
    log.info("ingest.start", manifestos_dir=str(manifestos_dir), tweets_dir=str(tweets_dir))

    report = ingest_manifestos(
        manifestos_dir=manifestos_dir,
        enricher=enricher,
        embedder=embedder,
        collection=manifestos_coll,
        bm25_path=bm25_path,
    )

    n_tweets = ingest_tweets(tweets_dir=tweets_dir, embedder=embedder, collection=tweets_coll)

    log.info(
        "ingest.done",
        manifesto_chunks=report.chunks_total,
        parties=report.parties,
        tweets=n_tweets,
        total_elapsed_s=round(time.monotonic() - t_total, 2),
    )


if __name__ == "__main__":
    main()
