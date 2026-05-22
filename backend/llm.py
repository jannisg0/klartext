"""LLM wrappers for both MLX (default) and Ollama (escape hatch).

``MlxLLM`` runs `mlx_lm` natively on Apple Silicon and is the
production path. ``OllamaLLM`` is kept behind ``LLM_BACKEND=ollama`` so
we can A/B against the goldset before removing the legacy backend.

Both expose the same two methods used by the rest of the app:

- ``chat_stream(messages) -> Iterator[str]`` for the answer LLM
- ``generate(prompt) -> str`` for the helper LLM (enrichment + query
  expansion)

The MLX runtime is injected behind a Protocol so tests don't need
``mlx_lm`` installed (it ships darwin-arm64 only).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from backend.prompt_builder import Message


@dataclass(frozen=True)
class GenerationConfig:
    model: str
    temperature: float = 0.2
    num_ctx: int = 8192

    def __post_init__(self) -> None:
        if not self.model:
            raise ValueError("GenerationConfig.model must not be empty")


# ---------------- MLX (default) ----------------


class MlxRuntime(Protocol):
    def stream_generate(
        self, *, model: Any, tokenizer: Any, prompt: str, max_tokens: int
    ) -> Iterator[Any]: ...

    def generate(self, *, model: Any, tokenizer: Any, prompt: str, max_tokens: int) -> str: ...


@dataclass
class MlxLLM:
    model: Any
    tokenizer: Any
    runtime: MlxRuntime
    config: GenerationConfig

    def _format(self, messages: Sequence[Message]) -> str:
        return self.tokenizer.apply_chat_template(
            [{"role": m.role, "content": m.content} for m in messages],
            add_generation_prompt=True,
            tokenize=False,
        )

    def chat_stream(self, messages: Sequence[Message]) -> Iterator[str]:
        prompt = self._format(messages)
        for response in self.runtime.stream_generate(
            model=self.model,
            tokenizer=self.tokenizer,
            prompt=prompt,
            max_tokens=self.config.num_ctx,
        ):
            text = getattr(response, "text", None)
            if text is None and isinstance(response, str):
                text = response
            if text:
                yield text

    def generate(self, prompt: str) -> str:
        text_prompt = self._format([Message(role="user", content=prompt)])
        return self.runtime.generate(
            model=self.model,
            tokenizer=self.tokenizer,
            prompt=text_prompt,
            max_tokens=self.config.num_ctx,
        )


# ---------------- Ollama (escape hatch) ----------------


class OllamaClient(Protocol):
    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        stream: bool,
        options: dict | None = None,
    ) -> Iterator[dict[str, Any]]: ...

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        stream: bool,
        options: dict | None = None,
    ) -> dict[str, Any]: ...


@dataclass
class OllamaLLM:
    client: OllamaClient
    config: GenerationConfig

    def _options(self) -> dict:
        return {
            "temperature": self.config.temperature,
            "num_ctx": self.config.num_ctx,
        }

    def chat_stream(self, messages: Sequence[Message]) -> Iterator[str]:
        payload = [{"role": m.role, "content": m.content} for m in messages]
        stream = self.client.chat(
            model=self.config.model,
            messages=payload,
            stream=True,
            options=self._options(),
        )
        for chunk in stream:
            token = chunk.get("message", {}).get("content", "")
            if token:
                yield token
            if chunk.get("done"):
                break

    def generate(self, prompt: str) -> str:
        response = self.client.generate(
            model=self.config.model,
            prompt=prompt,
            stream=False,
            options=self._options(),
        )
        return response.get("response", "")
