"""Thin Ollama wrapper.

Streams chat completions token-by-token for the main model
(``qwen3:14b``) and offers a one-shot ``generate`` for the helper
model (``qwen3:4b``) used by enrichment and query expansion. The
``ollama.Client`` instance is injected so tests run without a real
Ollama server.
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
