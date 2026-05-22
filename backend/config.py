"""Application settings loaded from environment variables and .env.

All knobs have defaults that match ``.env.example`` so the app boots
cleanly in dev. Production callers should still create a ``.env`` to
avoid surprises (e.g. CORS, log level).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_backend: Literal["mlx", "ollama"] = "mlx"
    mlx_model_llm: str = "mlx-community/gemma-4-e4b-it-OptiQ-4bit"
    mlx_model_reranker: str = "mlx-community/bge-reranker-v2-m3-4bit"
    mlx_max_tokens: int = 1024
    ollama_host: str = "http://localhost:11434"
    ollama_model_main: str = "qwen3:14b"
    ollama_model_helper: str = "qwen3:4b"
    chromadb_path: Path = Path("chromadb")
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    embedding_device: str = "mps"
    retrieval_top_k_dense: int = 30
    retrieval_top_k_sparse: int = 30
    rerank_top_k: int = 5
    rerank_score_threshold: float = 0.3
    query_expansion_enabled: bool = True
    contextual_enrichment_enabled: bool = True
    cors_origin: str = "http://localhost:5173"
    log_level: str = "INFO"

    @property
    def bm25_path(self) -> Path:
        return self.chromadb_path / "bm25_index.pkl"

    @property
    def enrichment_cache_path(self) -> Path:
        return self.chromadb_path / "enrichment_cache.json"


def get_settings() -> Settings:
    return Settings()
