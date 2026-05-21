"""Tests for pydantic request/response models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.models import (
    ChatMessage,
    ChatRequest,
    CitationItem,
    HealthResponse,
    SourceItem,
)


def test_chat_request_minimal_payload():
    req = ChatRequest(query="Was sagt SPD?")

    assert req.query == "Was sagt SPD?"
    assert req.party_filter is None
    assert req.politician is None
    assert req.history == []


def test_chat_request_rejects_empty_query():
    with pytest.raises(ValidationError):
        ChatRequest(query="")


def test_chat_request_rejects_whitespace_only_query():
    with pytest.raises(ValidationError):
        ChatRequest(query="   ")


def test_chat_request_history_accepts_user_and_assistant_roles():
    req = ChatRequest(
        query="q",
        history=[
            {"role": "user", "content": "earlier"},
            {"role": "assistant", "content": "answer"},
        ],
    )
    assert req.history[0].role == "user"
    assert req.history[1].role == "assistant"


def test_chat_message_rejects_unknown_role():
    with pytest.raises(ValidationError):
        ChatMessage(role="system", content="x")


def test_source_item_round_trip():
    s = SourceItem(
        chunk_id="spd_p12_c0",
        party="spd",
        page=12,
        section_path="Wirtschaft > Steuerpolitik",
        score=0.87,
        text_preview="Wir wollen...",
    )

    payload = s.model_dump()
    assert payload["chunk_id"] == "spd_p12_c0"
    assert payload["score"] == pytest.approx(0.87)


def test_citation_item_round_trip():
    c = CitationItem(party="spd", page=12, raw="[SPD – Seite 12]")
    assert c.model_dump()["party"] == "spd"


def test_health_response_with_all_systems_ok():
    h = HealthResponse(status="ok", ollama=True, chromadb=True, bm25=True, chunks=42)
    assert h.status == "ok"
    assert h.chunks == 42


def test_health_response_rejects_invalid_status():
    with pytest.raises(ValidationError):
        HealthResponse(status="weird", ollama=True, chromadb=True, bm25=True, chunks=0)
