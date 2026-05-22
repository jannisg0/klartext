"""Prompt construction for Neutral and Persona modes.

Both modes share the strict neutral system prompt with the retrieved
chunks injected as a ``[PARTEI – Seite X]`` block. Persona mode adds
a style-imitation overlay on top, referencing curated tweets only as
a tonal reference (never as factual content) and forces the
``[Stil-Imitation – keine echten Zitate]`` footer on the response.

Conversation history is capped at ``MAX_HISTORY`` messages so the
prompt sent to the LLM doesn't grow unbounded.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.retriever import Hit

MAX_HISTORY = 10


@dataclass(frozen=True)
class Message:
    role: str
    content: str


_NEUTRAL_SYSTEM = (
    "Du bist Klartext, ein politischer RAG-Assistent. Antworte AUSSCHLIESSLICH "
    "auf Basis der bereitgestellten Wahlprogramm-Auszüge. Regeln:\n"
    "- ZWINGEND: JEDE Aussage steht direkt vor einer Quellenangabe im Format "
    "[PARTEI – Seite X]. Keine Ausnahme. Eine Antwort ohne Quellenangaben ist "
    "ungültig.\n"
    "- Erfinde keine Zitate, keine Fakten, keine Zahlen.\n"
    "- Wenn der Kontext die Frage nicht beantwortet, sage das KLAR.\n"
    "- Wenn mehrere Parteien unterschiedliche Positionen haben, stelle sie "
    "gleichwertig nebeneinander.\n"
    "- Vermeide Wertungen wie 'gut', 'schlecht', 'sinnvoll'.\n"
    "\n"
    "BEISPIELE für korrektes Format:\n"
    "\n"
    "Frage: Wie steht die SPD zum Mindestlohn?\n"
    "Antwort: Die SPD fordert einen Mindestlohn von 15 Euro pro Stunde "
    "[SPD – Seite 2]. Sie will außerdem den Mindestlohn an die Lohnentwicklung "
    "koppeln [SPD – Seite 3].\n"
    "\n"
    "Frage: Was sagen die Parteien zur Vermögensteuer?\n"
    "Antwort: Die SPD will die Vermögensteuer wieder einführen "
    "[SPD – Seite 12]. Die CDU lehnt eine Vermögensteuer ab und setzt "
    "stattdessen auf Steuersenkungen für die Mittelschicht [CDU – Seite 5].\n"
    "\n"
    "Antworte jetzt auf die Frage des Nutzers im SELBEN Format. JEDER Satz "
    "muss mit [PARTEI – Seite X] enden, sonst ist die Antwort ungültig.\n"
    "\n"
    "Kontext:\n{chunks}"
)

_PERSONA_OVERLAY = (
    "\n\nDu sprichst im Stil von {politician_name}. Stilreferenz (NUR Tonfall, "
    "NICHT Inhalt erfinden):\n{tweets}\n"
    "Beende die Antwort mit: [Stil-Imitation – keine echten Zitate]"
)


def format_chunks_with_citations(hits: Sequence[Hit]) -> str:
    if not hits:
        return ""
    blocks: list[str] = []
    for hit in hits:
        party = str(hit.metadata.get("party", "?")).upper()
        page = hit.metadata.get("page", "?")
        blocks.append(f"[{party} – Seite {page}]\n{hit.text}")
    return "\n\n".join(blocks)


def _truncate_history(history: Sequence[Message]) -> list[Message]:
    return list(history[-MAX_HISTORY:])


def _system_message_neutral(hits: Sequence[Hit]) -> Message:
    return Message(
        role="system",
        content=_NEUTRAL_SYSTEM.format(chunks=format_chunks_with_citations(hits)),
    )


def build_neutral_prompt(
    *,
    query: str,
    hits: Sequence[Hit],
    history: Sequence[Message] | None = None,
) -> list[Message]:
    messages: list[Message] = [_system_message_neutral(hits)]
    if history:
        messages.extend(_truncate_history(history))
    messages.append(Message(role="user", content=query))
    return messages


def build_persona_prompt(
    *,
    query: str,
    hits: Sequence[Hit],
    politician_name: str,
    tweets: Sequence[str],
    history: Sequence[Message] | None = None,
) -> list[Message]:
    neutral_system = _system_message_neutral(hits).content
    persona_block = _PERSONA_OVERLAY.format(
        politician_name=politician_name,
        tweets="\n".join(f"- {t}" for t in tweets),
    )
    messages: list[Message] = [Message(role="system", content=neutral_system + persona_block)]
    if history:
        messages.extend(_truncate_history(history))
    messages.append(Message(role="user", content=query))
    return messages
