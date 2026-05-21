"""Tests for prompt construction.

Covers:
- format_chunks_with_citations renders [PARTY – Seite X] blocks
- build_neutral_prompt: system + history + user messages
- build_persona_prompt: persona overlay + final marker
- conversation history capped at MAX_HISTORY
"""

from __future__ import annotations

from backend.prompt_builder import (
    MAX_HISTORY,
    Message,
    build_neutral_prompt,
    build_persona_prompt,
    format_chunks_with_citations,
)
from backend.retriever import Hit


def _hit(chunk_id: str, text: str, party: str, page: int) -> Hit:
    return Hit(
        chunk_id=chunk_id,
        score=1.0,
        text=text,
        metadata={"party": party, "page": page, "section_path": "S > X"},
    )


def test_format_chunks_renders_citation_block_per_hit():
    hits = [
        _hit("spd_p12_c0", "Wir wollen Vermögensteuer.", "spd", 12),
        _hit("cdu_p5_c1", "Wir senken Steuern.", "cdu", 5),
    ]

    block = format_chunks_with_citations(hits)

    assert "[SPD – Seite 12]" in block
    assert "[CDU – Seite 5]" in block
    assert "Wir wollen Vermögensteuer." in block
    assert "Wir senken Steuern." in block
    assert block.index("[SPD") < block.index("[CDU")


def test_format_chunks_empty_returns_empty_string():
    assert format_chunks_with_citations([]) == ""


def test_neutral_prompt_starts_with_system_and_ends_with_user():
    hits = [_hit("spd_p1_c0", "body", "spd", 1)]
    messages = build_neutral_prompt(query="Was sagt SPD?", hits=hits)

    assert messages[0].role == "system"
    assert "Klartext" in messages[0].content
    assert "AUSSCHLIESSLICH" in messages[0].content
    assert "[SPD – Seite 1]" in messages[0].content
    assert messages[-1].role == "user"
    assert messages[-1].content == "Was sagt SPD?"


def test_neutral_prompt_includes_history_between_system_and_user():
    history = [
        Message(role="user", content="Frage 1"),
        Message(role="assistant", content="Antwort 1"),
    ]
    messages = build_neutral_prompt(
        query="Frage 2", hits=[_hit("spd_p1_c0", "b", "spd", 1)], history=history
    )

    roles = [m.role for m in messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert messages[1].content == "Frage 1"
    assert messages[2].content == "Antwort 1"


def test_neutral_prompt_truncates_history_to_max():
    history = [
        Message(role="user" if i % 2 == 0 else "assistant", content=f"m{i}")
        for i in range(MAX_HISTORY * 2)
    ]

    messages = build_neutral_prompt(
        query="now", hits=[_hit("spd_p1_c0", "b", "spd", 1)], history=history
    )

    # system + MAX_HISTORY most-recent + new user.
    history_msgs = messages[1:-1]
    assert len(history_msgs) == MAX_HISTORY
    assert history_msgs[-1].content == history[-1].content


def test_persona_prompt_appends_style_marker_in_system():
    hits = [_hit("gruene_p2_c0", "body", "gruene", 2)]
    messages = build_persona_prompt(
        query="Klima?",
        hits=hits,
        politician_name="Annalena Baerbock",
        tweets=["Klima ist Sicherheit.", "Diplomatie statt Eskalation."],
    )

    assert messages[0].role == "system"
    assert "Annalena Baerbock" in messages[0].content
    assert "Klima ist Sicherheit." in messages[0].content
    assert "[Stil-Imitation – keine echten Zitate]" in messages[0].content
    assert messages[-1].content == "Klima?"


def test_persona_prompt_carries_neutral_rules():
    """Persona must still enforce neutral citation rules over the chunks."""
    messages = build_persona_prompt(
        query="q",
        hits=[_hit("spd_p1_c0", "b", "spd", 1)],
        politician_name="X",
        tweets=["t"],
    )

    assert "[SPD – Seite 1]" in messages[0].content
    assert "[PARTEI – Seite X]" in messages[0].content
