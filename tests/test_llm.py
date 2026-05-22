"""Tests for the MLX LLM wrapper.

The MLX runtime is injected behind a Protocol so tests don't need
``mlx_lm`` installed (it ships darwin-arm64 only).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from backend.llm import GenerationConfig, MlxLLM
from backend.prompt_builder import Message


class _FakeTokenizer:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def apply_chat_template(self, messages, *, add_generation_prompt: bool, tokenize: bool) -> str:
        assert add_generation_prompt is True
        assert tokenize is False
        self.calls.append(list(messages))
        return "\n".join(f"{m['role']}:{m['content']}" for m in messages) + "\nassistant:"


@dataclass
class _FakeMlxRuntime:
    """Minimal stand-in for ``mlx_lm.stream_generate`` / ``mlx_lm.generate``."""

    chat_chunks: list[str] = field(default_factory=list)
    generate_response: str = ""
    stream_calls: list[dict[str, Any]] = field(default_factory=list)
    generate_calls: list[dict[str, Any]] = field(default_factory=list)

    def stream_generate(
        self, *, model: Any, tokenizer: Any, prompt: str, max_tokens: int
    ) -> Iterator[Any]:
        self.stream_calls.append({"prompt": prompt, "max_tokens": max_tokens})
        for token in self.chat_chunks:
            yield SimpleNamespace(text=token)

    def generate(self, *, model: Any, tokenizer: Any, prompt: str, max_tokens: int) -> str:
        self.generate_calls.append({"prompt": prompt, "max_tokens": max_tokens})
        return self.generate_response


_FAKE_MODEL = object()


def _build(runtime: _FakeMlxRuntime, **cfg_kwargs) -> tuple[MlxLLM, _FakeTokenizer]:
    tokenizer = _FakeTokenizer()
    config = GenerationConfig(model=cfg_kwargs.pop("model", "mlx-community/test"), **cfg_kwargs)
    llm = MlxLLM(model=_FAKE_MODEL, tokenizer=tokenizer, runtime=runtime, config=config)
    return llm, tokenizer


def test_chat_stream_yields_token_strings():
    runtime = _FakeMlxRuntime(chat_chunks=["Hallo ", "Welt", "."])
    llm, _ = _build(runtime)

    tokens = list(
        llm.chat_stream(
            [
                Message(role="system", content="sys"),
                Message(role="user", content="hi"),
            ]
        )
    )

    assert tokens == ["Hallo ", "Welt", "."]


def test_chat_stream_applies_chat_template_with_role_payload():
    runtime = _FakeMlxRuntime(chat_chunks=["x"])
    llm, tokenizer = _build(runtime)

    list(
        llm.chat_stream(
            [Message(role="system", content="rules"), Message(role="user", content="q")]
        )
    )

    assert tokenizer.calls == [
        [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "q"},
        ]
    ]
    assert runtime.stream_calls[0]["prompt"].startswith("system:rules\nuser:q")


def test_chat_stream_forwards_max_tokens_from_config():
    runtime = _FakeMlxRuntime(chat_chunks=["x"])
    llm, _ = _build(runtime, num_ctx=4096)

    list(llm.chat_stream([Message(role="user", content="q")]))

    assert runtime.stream_calls[0]["max_tokens"] == 4096


def test_generate_wraps_prompt_in_user_message_and_returns_text():
    runtime = _FakeMlxRuntime(generate_response="One sentence here.")
    llm, tokenizer = _build(runtime)

    out = llm.generate("Write one sentence.")

    assert out == "One sentence here."
    assert tokenizer.calls == [[{"role": "user", "content": "Write one sentence."}]]
    assert runtime.generate_calls[0]["prompt"].startswith("user:Write one sentence.")


def test_chat_stream_empty_chunks_produces_empty_iteration():
    runtime = _FakeMlxRuntime(chat_chunks=[])
    llm, _ = _build(runtime)

    tokens = list(llm.chat_stream([Message(role="user", content="q")]))

    assert tokens == []


def test_chat_stream_skips_empty_token_payloads():
    runtime = _FakeMlxRuntime(chat_chunks=["", "hi", ""])
    llm, _ = _build(runtime)

    tokens = list(llm.chat_stream([Message(role="user", content="q")]))

    assert tokens == ["hi"]


def test_chat_stream_accepts_plain_string_responses():
    """Some MLX wrappers yield raw strings rather than ``GenerationResponse``."""

    @dataclass
    class _StringRuntime:
        chunks: list[str]

        def stream_generate(self, *, model, tokenizer, prompt, max_tokens):
            yield from self.chunks

        def generate(self, *, model, tokenizer, prompt, max_tokens):  # pragma: no cover
            return ""

    runtime = _StringRuntime(chunks=["a", "b", "c"])
    tokenizer = _FakeTokenizer()
    llm = MlxLLM(
        model=_FAKE_MODEL,
        tokenizer=tokenizer,
        runtime=runtime,
        config=GenerationConfig(model="mlx-community/test"),
    )

    assert list(llm.chat_stream([Message(role="user", content="q")])) == ["a", "b", "c"]


def test_generation_config_requires_model_name():
    with pytest.raises(ValueError):
        GenerationConfig(model="")
