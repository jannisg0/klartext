"""FastAPI app: ``/health`` and ``/chat`` (SSE) endpoints.

The runtime pipeline lives in a ``Services`` container that's injected
once at app creation. Production callers use ``create_app()`` with no
arguments, which builds real services from environment settings; tests
pass a hand-built ``Services`` so they don't need MLX, ChromaDB,
BGE-M3, or a real cross-encoder running.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import run_in_threadpool

from backend.citation_verifier import verify_citations
from backend.config import Settings, get_settings
from backend.llm import MlxLLM, OllamaLLM
from backend.models import (
    ChatRequest,
    CitationItem,
    CitationsPayload,
    HealthResponse,
    SourceItem,
)
from backend.prompt_builder import (
    Message,
    build_neutral_prompt,
    build_persona_prompt,
)
from backend.reranker import CrossEncoderReranker
from backend.retriever import HybridRetriever, expand_query

log = structlog.get_logger(__name__)


@dataclass
class Services:
    settings: Settings
    retriever: HybridRetriever
    reranker: CrossEncoderReranker
    main_llm: MlxLLM | OllamaLLM
    helper_llm: MlxLLM | OllamaLLM
    persona_tweets: dict[str, list[str]]
    # ``llm_probe`` returns whether the LLM backend is ready. Surfaced on
    # ``/health`` under the legacy field name ``ollama`` to keep the
    # response shape stable for existing API consumers.
    llm_probe: Callable[[], bool]
    chromadb_probe: Callable[[], int]
    bm25_probe: Callable[[], bool]


def get_services(request: Request) -> Services:
    return request.app.state.services


def _text_preview(text: str, *, n: int = 200) -> str:
    return text[:n].rstrip()


def _sources_payload(hits) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for hit in hits:
        meta = hit.metadata
        items.append(
            SourceItem(
                chunk_id=hit.chunk_id,
                party=str(meta.get("party", "")),
                page=int(meta.get("page", 0)),
                section_path=str(meta.get("section_path", "")),
                score=float(hit.score),
                text_preview=_text_preview(hit.text),
            ).model_dump()
        )
    return items


def _citations_payload(verification) -> dict[str, Any]:
    def _item(c) -> dict[str, Any]:
        return CitationItem(party=c.party, page=c.page, raw=c.raw).model_dump()

    return CitationsPayload(
        verified=[_item(c) for c in verification.verified],
        unverified=[_item(c) for c in verification.unverified],
    ).model_dump()


async def _stream_chat(req: ChatRequest, services: Services) -> AsyncIterator[dict[str, Any]]:
    settings = services.settings

    # Each model call is sync (MLX, BGE-M3, cross-encoder). Run it on a
    # threadpool so other ASGI requests (notably /health) can still progress
    # and so the SSE response can flush each yield without head-of-line blocking.
    queries = await run_in_threadpool(
        expand_query,
        req.query,
        llm=services.helper_llm,
        enabled=settings.query_expansion_enabled,
    )

    raw_hits = await run_in_threadpool(
        services.retriever.retrieve,
        queries,
        top_k=max(settings.retrieval_top_k_dense, settings.retrieval_top_k_sparse),
        dense_top_k=settings.retrieval_top_k_dense,
        sparse_top_k=settings.retrieval_top_k_sparse,
        party_filter=req.party_filter,
    )
    reranked = await run_in_threadpool(
        services.reranker.rerank,
        query=req.query,
        hits=raw_hits,
        top_k=settings.rerank_top_k,
    )

    yield {"event": "sources", "data": json.dumps(_sources_payload(reranked.hits))}

    if reranked.below_threshold or not reranked.hits:
        log.info(
            "chat.empty_context",
            below_threshold=reranked.below_threshold,
            query=req.query,
        )
        yield {
            "event": "citations",
            "data": json.dumps(CitationsPayload(verified=[], unverified=[]).model_dump()),
        }
        yield {"event": "done", "data": "{}"}
        return

    history_msgs = [Message(role=m.role, content=m.content) for m in req.history]
    if req.politician:
        messages = build_persona_prompt(
            query=req.query,
            hits=reranked.hits,
            politician_name=req.politician,
            tweets=services.persona_tweets.get(req.politician, []),
            history=history_msgs,
        )
    else:
        messages = build_neutral_prompt(
            query=req.query,
            hits=reranked.hits,
            history=history_msgs,
        )

    parts: list[str] = []
    token_iter = services.main_llm.chat_stream(messages)

    # iterate the sync LLM stream one token at a time on a threadpool so the
    # event loop can yield each SSE frame as it arrives.
    sentinel = object()

    def _next_token():
        try:
            return next(token_iter)
        except StopIteration:
            return sentinel

    while True:
        token = await run_in_threadpool(_next_token)
        if token is sentinel:
            break
        parts.append(token)
        yield {"event": "token", "data": json.dumps({"text": token})}

    answer = "".join(parts)
    verification = verify_citations(answer, reranked.hits)
    yield {"event": "citations", "data": json.dumps(_citations_payload(verification))}
    yield {"event": "done", "data": "{}"}


_ServicesDep = Annotated[Services, Depends(get_services)]


def _register_routes(app: FastAPI) -> None:
    @app.get("/health", response_model=HealthResponse)
    async def health(services: _ServicesDep) -> HealthResponse:
        llm_ok = bool(services.llm_probe())
        chunks = int(services.chromadb_probe())
        bm25_ok = bool(services.bm25_probe())
        chromadb_ok = chunks > 0
        status = "ok" if (llm_ok and chromadb_ok and bm25_ok) else "degraded"
        return HealthResponse(
            status=status,
            ollama=llm_ok,
            chromadb=chromadb_ok,
            bm25=bm25_ok,
            chunks=chunks,
        )

    @app.post("/chat")
    async def chat(req: ChatRequest, services: _ServicesDep) -> EventSourceResponse:
        return EventSourceResponse(_stream_chat(req, services))


def _register_cors(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def create_app(services: Services | None = None) -> FastAPI:
    """Build the FastAPI app.

    When ``services`` is provided (tests), they're attached directly.
    Otherwise the lifespan builds the real production stack on startup.
    """
    if services is not None:
        app = FastAPI(title="Klartext")
        app.state.services = services
        _register_cors(app, services.settings)
        _register_routes(app)
        return app

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI):
        settings = get_settings()
        fastapi_app.state.services = build_production_services(settings)
        active_model = (
            settings.mlx_model_llm if settings.llm_backend == "mlx" else settings.ollama_model_main
        )
        log.info("app.started", backend=settings.llm_backend, model=active_model)
        yield

    app = FastAPI(title="Klartext", lifespan=lifespan)
    _register_cors(app, get_settings())
    _register_routes(app)
    return app


def _build_llm(
    settings: Settings,
) -> tuple[MlxLLM | OllamaLLM, MlxLLM | OllamaLLM, Callable[[], bool]]:
    """Build (main_llm, helper_llm, probe) for the configured backend."""
    from backend.llm import GenerationConfig

    if settings.llm_backend == "mlx":
        from mlx_lm import generate as mlx_generate
        from mlx_lm import load as mlx_load
        from mlx_lm import stream_generate as mlx_stream_generate

        @dataclass
        class _DefaultMlxRuntime:
            def stream_generate(self, *, model, tokenizer, prompt, max_tokens):
                return mlx_stream_generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens)

            def generate(self, *, model, tokenizer, prompt, max_tokens):
                return mlx_generate(
                    model, tokenizer, prompt=prompt, max_tokens=max_tokens, verbose=False
                )

        mlx_model, mlx_tokenizer = mlx_load(settings.mlx_model_llm)
        runtime = _DefaultMlxRuntime()
        cfg = GenerationConfig(model=settings.mlx_model_llm, num_ctx=settings.mlx_max_tokens)
        llm = MlxLLM(model=mlx_model, tokenizer=mlx_tokenizer, runtime=runtime, config=cfg)
        # Helper role reuses the same loaded weights — one set in memory.
        return llm, llm, lambda: True

    import ollama as ollama_lib

    ollama_client = ollama_lib.Client(host=settings.ollama_host)
    main_llm = OllamaLLM(
        client=ollama_client,
        config=GenerationConfig(model=settings.ollama_model_main),
    )
    helper_llm = OllamaLLM(
        client=ollama_client,
        config=GenerationConfig(model=settings.ollama_model_helper),
    )

    def _ollama_probe() -> bool:
        try:
            ollama_client.list()
        except Exception:
            return False
        return True

    return main_llm, helper_llm, _ollama_probe


def _build_scorer(settings: Settings):
    """Cross-encoder scorer. Tries MLX first, falls back to sentence-transformers."""
    try:
        from mlx_embeddings.utils import load as mlx_emb_load  # type: ignore[import-not-found]
    except Exception:
        log.info("reranker.mlx_unavailable", reason="mlx_embeddings not installed")
        return _build_sentence_transformers_scorer(settings)

    try:
        model, tokenizer = mlx_emb_load(settings.mlx_model_reranker)
    except Exception as exc:
        log.warning(
            "reranker.mlx_load_failed",
            model=settings.mlx_model_reranker,
            error=str(exc),
        )
        return _build_sentence_transformers_scorer(settings)

    import mlx.core as mx  # type: ignore[import-not-found]
    import numpy as _np

    class _MlxScorer:
        def score(self, pairs):
            texts_a = [q for q, _ in pairs]
            texts_b = [t for _, t in pairs]
            enc = tokenizer(
                texts_a,
                texts_b,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="np",
            )
            out = model(mx.array(enc["input_ids"]), mx.array(enc["attention_mask"]))
            logits = _np.asarray(out.logits if hasattr(out, "logits") else out)
            if logits.ndim == 2 and logits.shape[-1] == 1:
                logits = logits[:, 0]
            return (1.0 / (1.0 + _np.exp(-logits))).tolist()

    log.info("reranker.mlx_loaded", model=settings.mlx_model_reranker)
    return _MlxScorer()


def _build_sentence_transformers_scorer(settings: Settings):
    from sentence_transformers import CrossEncoder

    # CrossEncoder uses the fast tokenizer path; FlagReranker still calls
    # the removed slow-tokenizer ``prepare_for_model`` on transformers 5.x.
    reranker_model = CrossEncoder(settings.reranker_model, max_length=512)

    class _StScorer:
        def score(self, pairs):
            import numpy as _np

            scores = reranker_model.predict(
                [(q, t) for q, t in pairs],
                activation_fn=None,
                convert_to_numpy=True,
            )
            # Map raw logits to [0, 1] via sigmoid so the threshold (0.3) keeps meaning.
            return (1.0 / (1.0 + _np.exp(-scores))).tolist()

    log.info("reranker.st_loaded", model=settings.reranker_model)
    return _StScorer()


def build_production_services(settings: Settings) -> Services:
    """Wire up the real LLM + ChromaDB + BM25 + BGE-M3 + reranker stack."""
    import json as _json
    from pathlib import Path as _Path

    from FlagEmbedding import BGEM3FlagModel

    import chromadb
    from backend.bm25_index import Bm25Index

    chroma_client = chromadb.PersistentClient(path=str(settings.chromadb_path))
    manifestos = chroma_client.get_or_create_collection("klartext_manifestos")

    if not settings.bm25_path.exists():
        raise RuntimeError(
            f"BM25 index missing at {settings.bm25_path}. Run scripts/ingest.py first."
        )
    bm25 = Bm25Index.load(settings.bm25_path)

    embedding_model = BGEM3FlagModel(
        settings.embedding_model,
        use_fp16=False,
        device=settings.embedding_device,
    )

    class _Embedder:
        def embed(self, texts):
            out = embedding_model.encode(
                list(texts),
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
            return out["dense_vecs"].tolist()

    scorer = _build_scorer(settings)
    retriever = HybridRetriever(collection=manifestos, bm25=bm25, embedder=_Embedder())
    reranker = CrossEncoderReranker(scorer=scorer, threshold=settings.rerank_score_threshold)

    main_llm, helper_llm, llm_probe = _build_llm(settings)

    persona_tweets: dict[str, list[str]] = {}
    tweets_dir = _Path("data/tweets")
    for path in sorted(tweets_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        data = _json.loads(path.read_text(encoding="utf-8"))
        persona_tweets[data["politician"]] = [t["text"] for t in data.get("tweets", [])]

    return Services(
        settings=settings,
        retriever=retriever,
        reranker=reranker,
        main_llm=main_llm,
        helper_llm=helper_llm,
        persona_tweets=persona_tweets,
        llm_probe=llm_probe,
        chromadb_probe=manifestos.count,
        bm25_probe=lambda: settings.bm25_path.exists(),
    )


app = create_app()
