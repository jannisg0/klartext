# Konventionen

Knappe Referenz. Tieferer Stand in `CLAUDE.md` (Developer-Notiz für
KI-gestützte Arbeit).

---

## Code vs. UI-Sprache

- **Code, Variablen, Logging, Errors:** Englisch.
- **User-facing Strings, Prompts, Docs:** Deutsch.

Beispiel: `def party_from_pdf_path(...)` (en) → liefert
`"diegrünen"` (slug zum Dateinamen) → angezeigt im UI als
`"Bündnis 90 / Grüne"` (de).

---

## Idempotente IDs

| Typ | Schema | Beispiel |
|-----|--------|----------|
| Chunk | `{party}_p{page}_c{chunk_idx}` | `spd_p12_c3` |
| Tweet | `{politician}_{idx}` | `annalena_baerbock_0` |
| Citation | `[PARTEI – Seite X]` (en-dash) | `[SPD – Seite 12]` |

Der Party-Slug ist der lowercase-PDF-Filename-Stem. Re-Ingests
erzeugen dieselben IDs → keine Duplikate in ChromaDB.

---

## Python

- **Package Manager:** `uv` (immer `uv run …`).
- **Python:** `>=3.11` (Type-Hints PEP 604, `list[str]` statt
  `List[str]`).
- **Linter:** `ruff` (line-length 100, target py311, regelblöcke
  `E,F,I,B,UP,SIM,RUF` minus `RUF001/002/003` weil deutsche
  Umlaute und en-dashes intentional sind).
- **Tests:** `pytest`, async-mode=auto. Mocks via Protocol-Injection
  (keine `unittest.mock`-Magie), 112 Tests.
- **Logging:** `structlog` mit JSON-Output nach `logs/klartext.log`.
- **Conversation-History:** server-side gekappt auf 10 Messages
  (`MAX_HISTORY` in `backend/prompt_builder.py`).

Beispiel-Kommando:
```bash
uv run pytest -q
uv run ruff check
uv run ruff format --check
```

---

## Frontend

- **Vite + React + Tailwind**, **kein TypeScript**.
- **ESLint flat-config**, Prettier (`singleQuote: true, semi: false,
  printWidth: 100`).
- **Komponenten:** `.jsx`-Files exportieren **nur** Komponenten;
  Hooks/Reducer/Context in flachen `.js`-Files. Trennung erzwingt
  Vite Fast-Refresh-Compat.
- **State:** ein `useReducer` + Context (`frontend/src/state/
  chatStore.js`). Kein Redux/Zustand.

Build-Befehle:
```bash
cd frontend
npm run dev       # 127.0.0.1:5173 strict
npm run build
npm run lint
```

---

## Git-Discipline

Ausschließlich über den **git-agent**: `.claude/agents/git-agent.md`.

Hard-Rules (vom Agent erzwungen):
- **Conventional Commits:** `feat | fix | refactor | test | docs |
  chore | perf | style` mit optionalem Scope.
- **Atomare Commits:** ein logischer Change = ein Commit. Lieber zwei
  Commits als zwei Concerns in einem.
- **Sicherheits-Check vor Stage:** keine Secrets, keine Daten, keine
  Artefakte (`.env`, PDFs, ChromaDB-Inhalte, Pickle-Caches).
- **Push nur bei explizitem Auftrag.** Kein "und gleich pushen" als
  Default.
- **Keine `Co-Authored-By` Lines.** Keine `Generated with Claude
  Code` Footer. Keine Emojis in Commit-Messages.

Pre-commit Hooks (`.pre-commit-config.yaml`):
- ruff lint + format auf Python-Files
- trailing-whitespace, end-of-file-fixer, mixed-line-ending
- detect-private-key
- check-added-large-files (max 500 KB; `uv.lock` exempt weil als
  Lockfile gewollt)

---

## Datei-Layout

- `backend/` — alle Pipeline-Module + FastAPI-App
- `frontend/src/` — React + State + SSE-Client
- `scripts/` — One-shot CLIs (`ingest.py`, `eval.py`)
- `tests/` — Pytest-Suite, fasst alle Module ab (112 Tests)
- `data/` — `manifestos/` (PDFs, gitignored), `tweets/` (gitignored
  außer `_example.json`), `eval/goldset.json` (gitignored)
- `chromadb/` — Persistenz-Output, Inhalte gitignored
- `logs/` — strukturierte Logs, gitignored
- `docs/` — diese Dokumente plus `design/Klartext.html` (Claude-
  Design Handover, Session F)
- `.claude/agents/git-agent.md` — Commit-Discipline-Subagent

---

## Sessions A–H

Historische Implementierungs-Phasen, dokumentiert in `CLAUDE.md`:

| Session | Inhalt |
|---------|--------|
| A | `pdf_parser` + `chunker` + Tests |
| B | `enricher` + `scripts/ingest` end-to-end |
| C | `retriever` + `reranker` |
| D | `prompt_builder` + `llm` + `citation_verifier` |
| E | `backend/main.py` (FastAPI + SSE) |
| F | Frontend Design-Integration |
| F2 | Frontend ↔ Backend SSE-Wiring |
| G | `eval.py` + Goldset (siehe [`EVALUATION.md`](EVALUATION.md)) |
| H | Tuning auf Basis Eval-Ergebnissen |

---

Mehr Detail in der vollen `CLAUDE.md` (Stack-Map, vollständige
System-Prompts, vollständige Pipeline-Architektur).
