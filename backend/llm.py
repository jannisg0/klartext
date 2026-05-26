"""LLM wrapper for any OpenAI-compatible Chat Completions endpoint.

Both the MLX inference server (``mlx-lm --server``) and the Ollama
OpenAI gateway expose the same Chat Completions interface, so a single
``OpenAILLM`` handles both backends.  The caller wires the appropriate
``base_url`` at construction time; the runtime difference is invisible
here.

``GenerationConfig`` is unchanged — existing call-sites need no update.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend.prompt_builder import Message

if TYPE_CHECKING:
    from openai.resources.chat.completions import Completions


@dataclass(frozen=True)
class GenerationConfig:
    model: str
    temperature: float = 0.2
    num_ctx: int = 8192

    def __post_init__(self) -> None:
        if not self.model:
            raise ValueError("GenerationConfig.model must not be empty")


@dataclass
class OpenAILLM:
    """LLM wrapper around an OpenAI-compatible Chat Completions endpoint."""

    completions: Completions
    config: GenerationConfig

    def chat_stream(self, messages: Sequence[Message]) -> Iterator[str]:
        stream = self.completions.create(
            model=self.config.model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            stream=True,
            max_tokens=self.config.num_ctx,
            temperature=self.config.temperature,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    def generate(self, prompt: str) -> str:
        response = self.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            max_tokens=self.config.num_ctx,
            temperature=self.config.temperature,
        )
        return response.choices[0].message.content or ""
