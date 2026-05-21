"""Tests for the Ollama LLM wrapper.

The ollama client is injected so tests don't touch a real Ollama server.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from backend.llm import GenerationConfig, OllamaLLM
from backend.prompt_builder import Message


@dataclass
class _FakeOllama:
    """Minimal stand-in for ``ollama.Client``."""

    chat_chunks: list[str] = field(default_factory=list)
    generate_response: str = ""
    chat_calls: list[dict] = field(default_factory=list)
    generate_calls: list[dict] = field(default_factory=list)

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        stream: bool,
        options: dict | None = None,
    ) -> Iterator[dict[str, Any]]:
        self.chat_calls.append(
            {"model": model, "messages": messages, "stream": stream, "options": options}
        )
        assert stream is True
        for token in self.chat_chunks:
            yield {"message": {"content": token}, "done": False}
        yield {"message": {"content": ""}, "done": True}

    def generate(
        self, *, model: str, prompt: str, stream: bool, options: dict | None = None
    ) -> dict[str, Any]:
        self.generate_calls.append(
            {"model": model, "prompt": prompt, "stream": stream, "options": options}
        )
        return {"response": self.generate_response}


def test_chat_stream_yields_token_strings():
    client = _FakeOllama(chat_chunks=["Hallo ", "Welt", "."])
    llm = OllamaLLM(client=client, config=GenerationConfig(model="qwen3:14b"))

    tokens = list(
        llm.chat_stream(
            [
                Message(role="system", content="sys"),
                Message(role="user", content="hi"),
            ]
        )
    )

    assert tokens == ["Hallo ", "Welt", "."]


def test_chat_stream_forwards_model_and_messages():
    client = _FakeOllama(chat_chunks=["x"])
    llm = OllamaLLM(client=client, config=GenerationConfig(model="qwen3:14b"))

    list(
        llm.chat_stream(
            [Message(role="system", content="rules"), Message(role="user", content="q")]
        )
    )

    call = client.chat_calls[0]
    assert call["model"] == "qwen3:14b"
    assert call["messages"] == [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "q"},
    ]
    assert call["stream"] is True


def test_chat_stream_passes_generation_options():
    client = _FakeOllama(chat_chunks=["x"])
    config = GenerationConfig(model="qwen3:14b", temperature=0.5, num_ctx=4096)
    llm = OllamaLLM(client=client, config=config)

    list(llm.chat_stream([Message(role="user", content="q")]))

    opts = client.chat_calls[0]["options"]
    assert opts["temperature"] == 0.5
    assert opts["num_ctx"] == 4096


def test_generate_returns_response_text():
    client = _FakeOllama(generate_response="One sentence here.")
    llm = OllamaLLM(client=client, config=GenerationConfig(model="qwen3:4b"))

    out = llm.generate("Write one sentence.")

    assert out == "One sentence here."
    assert client.generate_calls[0]["model"] == "qwen3:4b"
    assert client.generate_calls[0]["stream"] is False
    assert client.generate_calls[0]["prompt"] == "Write one sentence."


def test_chat_stream_stops_at_done_event():
    """Empty chat_chunks still produces a clean iteration."""
    client = _FakeOllama(chat_chunks=[])
    llm = OllamaLLM(client=client, config=GenerationConfig(model="qwen3:14b"))

    tokens = list(llm.chat_stream([Message(role="user", content="q")]))

    assert tokens == []


def test_chat_stream_skips_empty_token_payloads():
    """Some Ollama versions emit final 'done' frames with empty content; skip them."""
    client = _FakeOllama(chat_chunks=["", "hi", ""])
    llm = OllamaLLM(client=client, config=GenerationConfig(model="qwen3:14b"))

    tokens = list(llm.chat_stream([Message(role="user", content="q")]))

    assert tokens == ["hi"]


def test_generation_config_requires_model_name():
    with pytest.raises(ValueError):
        GenerationConfig(model="")
