"""Tests for the OpenAI-compatible LLM wrapper.

``OpenAILLM`` is tested by injecting a fake ``ChatCompletionAPI`` so no
real inference server is needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast

import pytest
from openai.resources.chat.completions import Completions

from backend.llm import GenerationConfig, OpenAILLM
from backend.prompt_builder import Message


def _ns(content: str) -> Any:
    """Build a SimpleNamespace that mimics a streaming chunk's delta."""
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content))])


def _ns_non_stream(content: str) -> Any:
    """Build a SimpleNamespace mimicking a non-streaming completion response."""
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@dataclass
class _FakeCompletions:
    """Fake ChatCompletionAPI — records calls and returns configured responses."""

    stream_chunks: list[str] = field(default_factory=list)
    generate_response: str = ""
    calls: list[dict[str, Any]] = field(default_factory=list)

    def create(self, *, model, messages, stream, max_tokens, temperature, **kwargs):
        self.calls.append(
            {"model": model, "messages": messages, "stream": stream, "max_tokens": max_tokens}
        )
        if stream:
            return [_ns(t) for t in self.stream_chunks]
        return _ns_non_stream(self.generate_response)


def _build(completions: _FakeCompletions, **cfg_kwargs) -> OpenAILLM:
    config = GenerationConfig(model=cfg_kwargs.pop("model", "test-model"), **cfg_kwargs)
    return OpenAILLM(completions=cast(Completions, completions), config=config)


# ─── chat_stream ────────────────────────────────────────────────────────────


def test_chat_stream_yields_token_strings():
    fake = _FakeCompletions(stream_chunks=["Hallo ", "Welt", "."])
    llm = _build(fake)

    tokens = list(llm.chat_stream([Message(role="user", content="hi")]))

    assert tokens == ["Hallo ", "Welt", "."]


def test_chat_stream_passes_all_messages():
    fake = _FakeCompletions(stream_chunks=["x"])
    llm = _build(fake)

    list(
        llm.chat_stream(
            [Message(role="system", content="rules"), Message(role="user", content="q")]
        )
    )

    sent = fake.calls[0]["messages"]
    assert sent == [{"role": "system", "content": "rules"}, {"role": "user", "content": "q"}]


def test_chat_stream_uses_model_from_config():
    fake = _FakeCompletions(stream_chunks=["x"])
    llm = _build(fake, model="mlx-community/gemma-4-e4b-it-OptiQ-4bit")

    list(llm.chat_stream([Message(role="user", content="q")]))

    assert fake.calls[0]["model"] == "mlx-community/gemma-4-e4b-it-OptiQ-4bit"


def test_chat_stream_forwards_num_ctx_as_max_tokens():
    fake = _FakeCompletions(stream_chunks=["x"])
    llm = _build(fake, num_ctx=4096)

    list(llm.chat_stream([Message(role="user", content="q")]))

    assert fake.calls[0]["max_tokens"] == 4096


def test_chat_stream_passes_stream_true():
    fake = _FakeCompletions(stream_chunks=["x"])
    llm = _build(fake)

    list(llm.chat_stream([Message(role="user", content="q")]))

    assert fake.calls[0]["stream"] is True


def test_chat_stream_empty_produces_empty_iteration():
    fake = _FakeCompletions(stream_chunks=[])
    llm = _build(fake)

    assert list(llm.chat_stream([Message(role="user", content="q")])) == []


def test_chat_stream_skips_none_and_empty_content():
    """Chunks with None or empty delta.content are silently dropped."""

    @dataclass
    class _NullyCompletions:
        def create(self, *, model, messages, stream, max_tokens, temperature, **kwargs):
            return [
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None))]),
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=""))]),
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="hi"))]),
            ]

    llm = OpenAILLM(
        completions=cast(Completions, _NullyCompletions()),
        config=GenerationConfig(model="m"),
    )
    assert list(llm.chat_stream([Message(role="user", content="q")])) == ["hi"]


# ─── generate ───────────────────────────────────────────────────────────────


def test_generate_returns_response_text():
    fake = _FakeCompletions(generate_response="One sentence here.")
    llm = _build(fake)

    assert llm.generate("Write one sentence.") == "One sentence here."


def test_generate_wraps_prompt_as_user_message():
    fake = _FakeCompletions(generate_response="ok")
    llm = _build(fake)

    llm.generate("some prompt")

    assert fake.calls[0]["messages"] == [{"role": "user", "content": "some prompt"}]


def test_generate_passes_stream_false():
    fake = _FakeCompletions(generate_response="ok")
    llm = _build(fake)

    llm.generate("prompt")

    assert fake.calls[0]["stream"] is False


def test_generate_returns_empty_string_on_none_content():
    class _NoneContent:
        def create(self, *, model, messages, stream, max_tokens, temperature, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None))])

    llm = OpenAILLM(
        completions=cast(Completions, _NoneContent()), config=GenerationConfig(model="m")
    )
    assert llm.generate("prompt") == ""


# ─── GenerationConfig ───────────────────────────────────────────────────────


def test_generation_config_requires_non_empty_model():
    with pytest.raises(ValueError):
        GenerationConfig(model="")


def test_generation_config_defaults():
    cfg = GenerationConfig(model="some-model")
    assert cfg.temperature == pytest.approx(0.2)
    assert cfg.num_ctx == 8192
