"""End-to-end tests for the FastAPI app.

The Services dataclass is injected with fakes so tests don't need
MLX, ChromaDB, BGE-M3, or a cross-encoder running.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.llm import GenerationConfig, MlxLLM
from backend.main import Services, create_app
from backend.reranker import CrossEncoderReranker
from backend.retriever import HybridRetriever

# ---------- Fakes ----------


class _FakeBm25:
    def __init__(self, chunk_ids: list[str]):
        self.chunk_ids = chunk_ids

    def search(self, query: str, *, top_k: int):
        return [(cid, 0.5) for cid in self.chunk_ids[:top_k]]


@dataclass
class _FakeChroma:
    by_id: dict[str, tuple[str, dict]]

    def query(self, *, query_embeddings, n_results, where=None):
        ids = list(self.by_id.keys())[:n_results]
        return {"ids": [ids]}

    def get(self, *, ids: Sequence[str]) -> dict:
        ids = [cid for cid in ids if cid in self.by_id]
        return {
            "ids": list(ids),
            "documents": [self.by_id[cid][0] for cid in ids],
            "metadatas": [self.by_id[cid][1] for cid in ids],
        }

    def count(self) -> int:
        return len(self.by_id)


@dataclass
class _FakeEmbedder:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 2.0, 3.0] for _ in texts]


class _FakeTokenizer:
    def apply_chat_template(self, messages, *, add_generation_prompt, tokenize):
        return "\n".join(f"{m['role']}:{m['content']}" for m in messages)


@dataclass
class _FakeMlxRuntime:
    main_chunks: list[str] = field(default_factory=list)
    helper_response: str = ""

    def stream_generate(
        self, *, model: Any, tokenizer: Any, prompt: str, max_tokens: int
    ) -> Iterator[Any]:
        for token in self.main_chunks:
            yield SimpleNamespace(text=token)

    def generate(self, *, model: Any, tokenizer: Any, prompt: str, max_tokens: int) -> str:
        return self.helper_response


@dataclass
class _FakeScorer:
    score_map: dict[str, float]

    def score(self, pairs):
        return [self.score_map.get(t, 0.5) for _, t in pairs]


def _build_services(
    *,
    main_chunks: list[str] | None = None,
    score_map: dict[str, float] | None = None,
    threshold: float = 0.3,
    persona_tweets: dict[str, list[str]] | None = None,
    llm_ok: bool = True,
    bm25_ok: bool = True,
    chroma_docs: dict[str, tuple[str, dict]] | None = None,
) -> Services:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    docs = (
        chroma_docs
        if chroma_docs is not None
        else {
            "spd_p12_c0": (
                "Wir wollen Vermoegensteuer.",
                {"party": "spd", "page": 12, "section_path": "Wirtschaft > Steuern"},
            ),
            "cdu_p5_c0": (
                "Wir senken Steuern.",
                {"party": "cdu", "page": 5, "section_path": "Wirtschaft > Steuern"},
            ),
        }
    )
    chroma = _FakeChroma(by_id=docs)
    bm25 = _FakeBm25(chunk_ids=list(docs.keys()))
    embedder = _FakeEmbedder()
    retriever = HybridRetriever(collection=chroma, bm25=bm25, embedder=embedder)

    scorer = _FakeScorer(score_map=score_map or {})
    reranker = CrossEncoderReranker(scorer=scorer, threshold=threshold)

    runtime = _FakeMlxRuntime(
        main_chunks=main_chunks if main_chunks is not None else ["Hallo ", "Welt", "."],
        helper_response="alt 1\nalt 2",
    )
    tokenizer = _FakeTokenizer()
    llm = MlxLLM(
        model=object(),
        tokenizer=tokenizer,
        runtime=runtime,
        config=GenerationConfig(model="mlx-community/test"),
    )

    return Services(
        settings=settings,
        retriever=retriever,
        reranker=reranker,
        main_llm=llm,
        helper_llm=llm,
        persona_tweets=persona_tweets or {},
        llm_probe=lambda: llm_ok,
        chromadb_probe=chroma.count,
        bm25_probe=lambda: bm25_ok,
    )


def _parse_sse(text: str) -> list[tuple[str, dict | str]]:
    """Parse text/event-stream payload into (event_name, parsed_data) tuples."""
    events: list[tuple[str, dict | str]] = []
    cur_event: str | None = None
    cur_data: list[str] = []
    for line in [*text.splitlines(), ""]:
        if line.startswith("event:"):
            cur_event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            cur_data.append(line.split(":", 1)[1].strip())
        elif line == "" and cur_event is not None:
            raw = "\n".join(cur_data)
            try:
                parsed: dict | str = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                parsed = raw
            events.append((cur_event, parsed))
            cur_event = None
            cur_data = []
    return events


# ---------- Health ----------


def test_health_all_systems_ok_returns_status_ok():
    score_map = {"Wir wollen Vermoegensteuer.": 0.9}
    app = create_app(services=_build_services(score_map=score_map))
    client = TestClient(app)

    resp = client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["ollama"] is True
    assert body["chromadb"] is True
    assert body["bm25"] is True
    assert body["chunks"] >= 2


def test_health_broken_llm_returns_degraded():
    app = create_app(services=_build_services(llm_ok=False))
    client = TestClient(app)

    resp = client.get("/health")

    body = resp.json()
    assert body["status"] == "degraded"
    assert body["ollama"] is False


def test_health_no_chunks_returns_degraded():
    app = create_app(services=_build_services(chroma_docs={}))
    client = TestClient(app)

    resp = client.get("/health")

    body = resp.json()
    assert body["status"] == "degraded"
    assert body["chromadb"] is False
    assert body["chunks"] == 0


# ---------- Chat ----------


def test_chat_streams_sources_then_tokens_then_citations_then_done():
    score_map = {"Wir wollen Vermoegensteuer.": 0.9, "Wir senken Steuern.": 0.8}
    services = _build_services(
        main_chunks=["Die SPD ", "[SPD – Seite 12]", " sagt Y."],
        score_map=score_map,
    )
    app = create_app(services=services)
    client = TestClient(app)

    resp = client.post(
        "/chat",
        json={"query": "Was sagt SPD zur Vermögensteuer?", "party_filter": ["spd", "cdu"]},
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)

    names = [e[0] for e in events]
    assert names[0] == "sources"
    assert "token" in names
    assert "citations" in names
    assert names[-1] == "done"
    assert names.index("sources") < names.index("token") < names.index("citations")


def test_chat_sources_event_contains_top_hits_with_scores():
    score_map = {"Wir wollen Vermoegensteuer.": 0.9, "Wir senken Steuern.": 0.4}
    app = create_app(services=_build_services(score_map=score_map))
    client = TestClient(app)

    resp = client.post("/chat", json={"query": "Steuern?"})

    events = dict(_parse_sse(resp.text))
    sources = events["sources"]
    assert isinstance(sources, list)
    assert any(s["chunk_id"] == "spd_p12_c0" for s in sources)
    assert any(s["score"] == pytest.approx(0.9) for s in sources)


def test_chat_below_threshold_emits_empty_sources_and_skips_tokens():
    score_map = {"Wir wollen Vermoegensteuer.": 0.05, "Wir senken Steuern.": 0.05}
    app = create_app(services=_build_services(score_map=score_map, threshold=0.3))
    client = TestClient(app)

    resp = client.post("/chat", json={"query": "Steuern?"})

    events = _parse_sse(resp.text)
    names = [e[0] for e in events]
    assert "token" not in names
    sources_event = next(e for e in events if e[0] == "sources")
    assert sources_event[1] == []
    assert names[-1] == "done"


def test_chat_citations_event_reports_verified_and_unverified():
    score_map = {"Wir wollen Vermoegensteuer.": 0.9}
    services = _build_services(
        main_chunks=["A [SPD – Seite 12] und B [SPD – Seite 99]."],
        score_map=score_map,
    )
    app = create_app(services=services)
    client = TestClient(app)

    resp = client.post("/chat", json={"query": "Steuern?", "party_filter": ["spd"]})
    events = dict(_parse_sse(resp.text))

    cits = events["citations"]
    verified_pages = {c["page"] for c in cits["verified"]}
    unverified_pages = {c["page"] for c in cits["unverified"]}
    assert 12 in verified_pages
    assert 99 in unverified_pages


def test_chat_persona_mode_uses_politician_tweets():
    score_map = {"Wir wollen Vermoegensteuer.": 0.9}
    services = _build_services(
        main_chunks=["Stilantwort"],
        score_map=score_map,
        persona_tweets={"annalena_baerbock": ["Klima ist Sicherheit."]},
    )
    app = create_app(services=services)
    client = TestClient(app)

    resp = client.post(
        "/chat",
        json={"query": "Klima?", "politician": "annalena_baerbock"},
    )

    assert resp.status_code == 200
    events = dict(_parse_sse(resp.text))
    assert "sources" in events
    assert "done" in events


def test_chat_rejects_empty_query():
    app = create_app(services=_build_services())
    client = TestClient(app)

    resp = client.post("/chat", json={"query": ""})

    assert resp.status_code == 422


def test_app_sets_cors_origin_from_settings():
    services = _build_services()
    services.settings.cors_origin = "http://example.com"
    app = create_app(services=services)
    client = TestClient(app)

    resp = client.options(
        "/chat",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert resp.headers.get("access-control-allow-origin") == "http://example.com"
