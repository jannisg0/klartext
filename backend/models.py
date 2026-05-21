"""Pydantic request and response models for the public API.

These shapes are the contract between the React frontend and the
backend; they're also what the SSE events carry as JSON payloads.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    query: str = Field(min_length=1)
    party_filter: list[str] | None = None
    politician: str | None = None
    history: list[ChatMessage] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def _query_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class SourceItem(BaseModel):
    chunk_id: str
    party: str
    page: int
    section_path: str
    score: float
    text_preview: str


class CitationItem(BaseModel):
    party: str
    page: int
    raw: str


class CitationsPayload(BaseModel):
    verified: list[CitationItem]
    unverified: list[CitationItem]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    ollama: bool
    chromadb: bool
    bm25: bool
    chunks: int
