# docs/

Projektdokumentation außerhalb von `README.md` und `CLAUDE.md`.
Jede Datei behandelt ein einzelnes Thema und ist quergeschnitten
verlinkt.

---

## Dokumenten-Index

| Datei | Inhalt | Zielgruppe |
|-------|--------|------------|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Pipeline-Übersicht + Modul-Map + Datenfluss | Wer das System verstehen will |
| [`PIPELINE.md`](PIPELINE.md) | Ingestion + Runtime im Detail mit Default-Werten | Contributors, Reviewer |
| [`DESIGN-DECISIONS.md`](DESIGN-DECISIONS.md) | Trade-offs hinter den großen Entscheidungen | Reviewer, neue Maintainer |
| [`SETUP.md`](SETUP.md) | Schritt-für-Schritt-Installation auf Apple Silicon | Erste Inbetriebnahme |
| [`API.md`](API.md) | `/health` + `/chat` SSE-Contract mit JSON-Beispielen | Frontend-Integration, Third-Party-Clients |
| [`FRONTEND.md`](FRONTEND.md) | Komponenten-Layout + Dev-Loop + SSE-Client | Frontend-Arbeit |
| [`EVALUATION.md`](EVALUATION.md) | Goldset + ragas-Plan (Session G) | Qualitätsmessung |
| [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) | FAQ zu bekannten Stolperern | Debugging |
| [`CONVENTIONS.md`](CONVENTIONS.md) | Code-Stil + Git-Discipline + Layout | Contributors |

---

## `design/`

Visueller Entwurfs-Ort für die Frontend-Integration. Die Datei
`Klartext.html` ist die Übergabe aus **Claude Design** — ein
einzelnes statisches HTML-Dokument mit Tailwind-Klassen, das alle
UI-Zustände abbildet (Empty, Streaming, Citations, FilterBar +
PersonaSelector, Below-Threshold, Error).

In **Session F** wurde dieses Markup pro Region in JSX-Komponenten
unter `frontend/src/components/` übersetzt. Tailwind-Klassen blieben
im ersten Durchgang unverändert; Restrukturierung passierte erst
nach Sign-off pro Zustand.

`Klartext.html` ist **Referenz, kein Build-Artefakt** — keine
Auslieferung an den Browser, kein Pipeline-Step.
