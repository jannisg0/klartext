"""Tests for the BM25 sparse-index wrapper."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.bm25_index import Bm25Index, tokenize_for_bm25


def test_tokenize_lowercases_and_drops_punctuation():
    tokens = tokenize_for_bm25("Vermögensteuer: ja! 15-Euro Mindestlohn.")
    assert "vermögensteuer" in tokens
    assert "ja" in tokens
    assert "15" in tokens
    assert "euro" in tokens
    assert "mindestlohn" in tokens
    for t in tokens:
        assert ":" not in t and "." not in t and "!" not in t


def test_build_and_score_returns_ranked_chunk_ids():
    docs = {
        "spd_p1_c0": "Wir wollen eine Vermögensteuer einführen.",
        "spd_p2_c0": "Mindestlohn auf 15 Euro pro Stunde.",
        "cdu_p1_c0": "Steuersenkungen für die Mittelschicht.",
    }
    index = Bm25Index.build(docs)

    results = index.search("Vermögensteuer", top_k=2)

    assert results[0][0] == "spd_p1_c0"
    assert all(score >= 0 for _, score in results)
    assert len(results) == 2


def test_search_returns_empty_when_no_token_overlap():
    docs = {"a": "hello world"}
    index = Bm25Index.build(docs)
    assert index.search("xyz123notpresent", top_k=5)[0][1] == pytest.approx(0)


def test_save_and_load_roundtrip(tmp_path: Path):
    docs = {
        "spd_p1_c0": "Vermögensteuer einführen.",
        "spd_p2_c0": "Mindestlohn 15 Euro.",
    }
    index = Bm25Index.build(docs)
    path = tmp_path / "bm25.pkl"
    index.save(path)

    loaded = Bm25Index.load(path)
    top_orig = index.search("Vermögensteuer", top_k=1)
    top_loaded = loaded.search("Vermögensteuer", top_k=1)
    assert top_orig[0][0] == top_loaded[0][0]
    assert top_orig[0][1] == pytest.approx(top_loaded[0][1])


def test_build_rejects_empty_corpus():
    with pytest.raises(ValueError):
        Bm25Index.build({})
