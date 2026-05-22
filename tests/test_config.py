"""Tests for the application settings loader.

Settings are read from environment variables (and optionally a .env
file). All knobs have safe defaults so the app can boot in dev.
"""

from __future__ import annotations

import pytest

from backend.config import Settings


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch):
    # Stop any .env from leaking through.
    for var in [
        "LLM_BACKEND",
        "MLX_MODEL_LLM",
        "MLX_MODEL_RERANKER",
        "MLX_MAX_TOKENS",
        "OLLAMA_HOST",
        "OLLAMA_MODEL_MAIN",
        "OLLAMA_MODEL_HELPER",
        "CHROMADB_PATH",
        "EMBEDDING_MODEL",
        "RERANKER_MODEL",
        "EMBEDDING_DEVICE",
        "RETRIEVAL_TOP_K_DENSE",
        "RETRIEVAL_TOP_K_SPARSE",
        "RERANK_TOP_K",
        "RERANK_SCORE_THRESHOLD",
        "QUERY_EXPANSION_ENABLED",
        "CONTEXTUAL_ENRICHMENT_ENABLED",
        "CORS_ORIGIN",
        "LOG_LEVEL",
    ]:
        monkeypatch.delenv(var, raising=False)

    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert s.llm_backend == "mlx"
    assert s.mlx_model_llm == "mlx-community/gemma-4-e4b-it-OptiQ-4bit"
    assert s.mlx_model_reranker == "mlx-community/bge-reranker-v2-m3-4bit"
    assert s.mlx_max_tokens == 1024
    assert s.ollama_host == "http://localhost:11434"
    assert s.ollama_model_main == "qwen3:14b"
    assert s.ollama_model_helper == "qwen3:4b"
    assert str(s.chromadb_path) == "chromadb"
    assert s.embedding_model == "BAAI/bge-m3"
    assert s.reranker_model == "BAAI/bge-reranker-v2-m3"
    assert s.embedding_device == "mps"
    assert s.retrieval_top_k_dense == 30
    assert s.retrieval_top_k_sparse == 30
    assert s.rerank_top_k == 5
    assert s.rerank_score_threshold == pytest.approx(0.3)
    assert s.query_expansion_enabled is True
    assert s.contextual_enrichment_enabled is True
    assert s.cors_origin == "http://localhost:5173"
    assert s.log_level == "INFO"


def test_settings_reads_environment_variables(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setenv("MLX_MODEL_LLM", "mlx-community/Qwen3.5-4B-MLX-4bit")
    monkeypatch.setenv("MLX_MAX_TOKENS", "2048")
    monkeypatch.setenv("OLLAMA_MODEL_MAIN", "qwen3:27b")
    monkeypatch.setenv("RERANK_SCORE_THRESHOLD", "0.45")
    monkeypatch.setenv("QUERY_EXPANSION_ENABLED", "false")
    monkeypatch.setenv("CORS_ORIGIN", "http://example.com")

    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert s.llm_backend == "ollama"
    assert s.mlx_model_llm == "mlx-community/Qwen3.5-4B-MLX-4bit"
    assert s.mlx_max_tokens == 2048
    assert s.ollama_model_main == "qwen3:27b"
    assert s.rerank_score_threshold == pytest.approx(0.45)
    assert s.query_expansion_enabled is False
    assert s.cors_origin == "http://example.com"


def test_bm25_path_derives_from_chromadb_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CHROMADB_PATH", "/tmp/klartext-chroma")

    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert str(s.bm25_path) == "/tmp/klartext-chroma/bm25_index.pkl"


def test_enrichment_cache_path_derives_from_chromadb_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CHROMADB_PATH", "/tmp/klartext-chroma")

    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert str(s.enrichment_cache_path) == "/tmp/klartext-chroma/enrichment_cache.json"
