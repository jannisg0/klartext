# Klartext – Final Init-Prompt (Pro + Git-Agent + Pre-Commit, Mai 2026)

Einfügen in eine neue Claude Code Session in einem leeren Ordner `klartext/`.

---

## Prompt

```
Du initialisierst KLARTEXT – einen lokalen politischen RAG-Chatbot mit
professioneller Pipeline-Qualität. Nicht "Chunk-Embed-Retrieve" auf Bachelor-
Niveau, sondern ein messbar gutes System mit Reranking, Hybrid Retrieval,
Contextual Chunks, Eval-Harness, sauberer Git-Discipline und Pre-Commit-Hooks.

Der Name verpflichtet: klare Sprache, verifizierte Quellenangaben, keine
halluzinierten Zitate.

Arbeite die Schritte strikt der Reihe nach ab. Code in den Pipeline-Modulen
wird NICHT in diesem Schritt geschrieben – nur Skeleton + Konfig + Doku.

═══════════════════════════════════════════════════════════════════════
STACK (Mai 2026)
═══════════════════════════════════════════════════════════════════════
- Package Manager:  uv (pyproject.toml + uv.lock)
- Python:           >=3.11
- LLM Hauptmodell:  Ollama qwen3:14b (16GB Mac) oder qwen3.6:27b (32GB)
- LLM Hilfsmodell:  Ollama qwen3:4b (Contextual Enrichment + Query Expansion)
- Embeddings:       BAAI/bge-m3 (dense + sparse aus einem Modell)
- Reranker:         BAAI/bge-reranker-v2-m3 (Cross-Encoder)
- Vector DB:        ChromaDB (lokal, persistiert)
- Sparse Index:     rank_bm25 (in-memory, persistiert als pickle)
- PDF-Parsing:      PyMuPDF (layout-aware mit Heading-Detection)
- Eval:             ragas + manuell kuratierter Goldset
- Backend:          FastAPI + Server-Sent Events
- Frontend:         React (Vite) + Tailwind, dunkles Theme, kein TS
- Linting:          ruff (lint + format) via pre-commit
- Logging:          structlog (strukturierte Logs für Eval)
- Git-Discipline:   dedizierter Subagent (.claude/agents/git-agent.md)

═══════════════════════════════════════════════════════════════════════
PIPELINE-ARCHITEKTUR
═══════════════════════════════════════════════════════════════════════

INGESTION (einmalig pro Datenupdate)
─────────────────────────────────────
1. PyMuPDF parst PDF mit Layout-Infos (Fontsize, Position)
2. Heading-Detection: Top-3 Fontsizes als H1/H2/H3 klassifizieren
3. Document Tree bauen: party → section → subsection → paragraphs
4. Structure-aware Chunking:
   - chunk_size=500 tokens, overlap=100
   - NIE über Sektionsgrenzen chunken
   - section_path als Metadatum: "Wirtschaft > Steuerpolitik > Vermögensteuer"
5. Contextual Enrichment (Anthropic-Methode):
   - Pro Chunk Call an qwen3:4b:
     "Document-Kontext: {section_path}
      Chunk: {chunk}
      Schreibe EINEN Satz der erklärt wo dieser Chunk im Wahlprogramm
      sitzt. Nur den Satz, sonst nichts."
   - Generierten Satz vor den Chunk kleben
   - Caching: SHA256 von Chunk-Inhalt als Key, damit Re-Ingests schnell sind
6. Embedding mit BGE-M3:
   - dense vector → ChromaDB Collection klartext_manifestos
   - sparse weights → BM25 Index (Term-Frequencies)
7. Metadaten: {party, section_path, page, chunk_id, context, source_pdf}
8. Tweets analog ohne Chunking → Collection klartext_tweets

RUNTIME (pro User-Query)
─────────────────────────────────────
1. Query empfangen + Filter (party_filter, politician)
2. Query Expansion via qwen3:4b (toggelbar):
   "Generiere 2 alternative deutsche Formulierungen dieser Frage."
   → 3 Queries total
3. Hybrid Retrieval (für JEDE Query):
   a) Dense via BGE-M3 + ChromaDB → top 30
   b) Sparse via rank_bm25 → top 30
4. RRF Fusion: alle Listen poolen, Score 1/(60+rank) summieren, top 30 keepen
5. Cross-Encoder Rerank mit bge-reranker-v2-m3:
   - (query, chunk) Paare scoren
   - Top 5 keepen
   - Score < threshold (default 0.3) → leeres Ergebnis signalisieren
6. Prompt-Konstruktion (siehe System-Prompts unten)
7. LLM-Generation mit qwen3:14b/27b, streaming
8. Citation Verification post-hoc:
   - Regex \[(\w+) – Seite (\d+)\] aus Antwort extrahieren
   - Jede gegen retrieved chunks prüfen
   - Unverifizierte → Warning event im SSE-Stream
9. SSE-Stream-Reihenfolge:
   - sources event (Top 5 mit scores)
   - token events (LLM stream)
   - citations event (verified / unverified Liste)
   - done event

EVALUATION
─────────────────────────────────────
Goldset in data/eval/goldset.json mit ~30-50 manuell kuratierten Q&A-Paaren:
{
  "question": "Was sagt die SPD zur Vermögensteuer?",
  "party_filter": ["spd"],
  "expected_chunks": ["spd_p12_c3", "spd_p13_c1"],
  "expected_answer_contains": ["Vermögensteuer", "Wiedereinführung"]
}

scripts/eval.py:
- Lädt Goldset
- Führt komplette Pipeline pro Frage aus
- Berechnet ragas Metriken: context_precision, context_recall,
  faithfulness, answer_relevance
- Ausgabe: logs/eval_{timestamp}.json + Markdown-Summary

═══════════════════════════════════════════════════════════════════════
SYSTEM-PROMPTS (gehört nach prompt_builder.py später)
═══════════════════════════════════════════════════════════════════════

NEUTRAL-MODUS:
"Du bist Klartext, ein politischer RAG-Assistent. Antworte AUSSCHLIESSLICH
auf Basis der bereitgestellten Wahlprogramm-Auszüge. Regeln:
- Jede Aussage mit [PARTEI – Seite X] zitieren
- Erfinde keine Zitate, keine Fakten, keine Zahlen
- Wenn der Kontext die Frage nicht beantwortet, sage das KLAR
- Wenn mehrere Parteien unterschiedliche Positionen haben, stelle sie
  gleichwertig nebeneinander
- Vermeide Wertungen wie 'gut', 'schlecht', 'sinnvoll'
Kontext: {chunks_with_citations}"

PERSONA-MODUS (zusätzlich):
"Du sprichst im Stil von {politician_name}. Stilreferenz (NUR Tonfall,
NICHT Inhalt erfinden): {tweets}
Beende die Antwort mit: [Stil-Imitation – keine echten Zitate]"

═══════════════════════════════════════════════════════════════════════
KONVENTIONEN
═══════════════════════════════════════════════════════════════════════
- Code, Variablen, Logging: Englisch
- User-facing Strings, Prompts: Deutsch
- Idempotente IDs: chunks {party}_{page}_{chunk_idx}, tweets {politician}_{idx}
- ChromaDB Collections: klartext_manifestos, klartext_tweets
- BM25 Index: chromadb/bm25_index.pkl
- Conversation History: serverseitig max 10 Messages an LLM
- Alle Python-Befehle via `uv run`
- Linting: ruff (line-length 100, py311 target)
- Tests in tests/, ausgeführt via `uv run pytest`
- Logging: structlog mit JSON-Output nach logs/klartext.log
- Git-Workflow: ausschließlich über git-agent (siehe .claude/agents/)

═══════════════════════════════════════════════════════════════════════
SCHRITT 1 – VERZEICHNISSTRUKTUR
═══════════════════════════════════════════════════════════════════════

Lege folgende Struktur an (mit .gitkeep wo Ordner sonst leer wären):

klartext/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── .gitignore
├── .env.example
├── .pre-commit-config.yaml
├── .claude/
│   └── agents/
│       └── git-agent.md
├── data/
│   ├── manifestos/.gitkeep
│   ├── tweets/_example.json
│   └── eval/_example.json
├── scripts/
│   ├── ingest.py             ← leerer Stub, Implementation in Session B
│   └── eval.py               ← leerer Stub, Implementation in Session G
├── backend/
│   ├── __init__.py
│   ├── main.py               ← leerer Stub
│   ├── config.py             ← leerer Stub
│   ├── models.py             ← leerer Stub
│   ├── pdf_parser.py         ← leerer Stub, Session A
│   ├── chunker.py            ← leerer Stub, Session A
│   ├── enricher.py           ← leerer Stub, Session B
│   ├── retriever.py          ← leerer Stub, Session C
│   ├── reranker.py           ← leerer Stub, Session C
│   ├── prompt_builder.py     ← leerer Stub, Session D
│   ├── llm.py                ← leerer Stub, Session D
│   └── citation_verifier.py  ← leerer Stub, Session D
├── frontend/                  ← Vite Setup kommt in Session F
│   └── .gitkeep
├── tests/
│   └── .gitkeep
├── chromadb/.gitkeep         ← Inhalte gitignored
└── logs/.gitkeep             ← Inhalte gitignored

═══════════════════════════════════════════════════════════════════════
SCHRITT 2 – pyproject.toml
═══════════════════════════════════════════════════════════════════════

[project]
name = "klartext"
version = "0.1.0"
description = "Lokaler politischer RAG-Chatbot für ein Hochschulprojekt"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "chromadb>=0.5",
    "sentence-transformers>=3.2",
    "FlagEmbedding>=1.3",
    "pymupdf>=1.24",
    "rank-bm25>=0.2.2",
    "ollama>=0.4",
    "sse-starlette>=2.1",
    "python-dotenv>=1.0",
    "tqdm>=4.66",
    "structlog>=24.4",
    "ragas>=0.2",
]

[dependency-groups]
dev = [
    "ruff>=0.7",
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pre-commit>=4.0",
]

[tool.uv]
package = false

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "RUF"]

[tool.ruff.format]
quote-style = "double"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

═══════════════════════════════════════════════════════════════════════
SCHRITT 3 – .gitignore
═══════════════════════════════════════════════════════════════════════

# Python / uv
__pycache__/
*.pyc
*.pyo
.venv/
.python-version

# Project Artifacts
.env
.env.*
!.env.example
chromadb/*
!chromadb/.gitkeep
logs/*
!logs/.gitkeep
*.log

# Node
node_modules/
dist/
frontend/dist/

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp

# Data – nicht ins Repo
data/manifestos/*
!data/manifestos/.gitkeep
data/tweets/*
!data/tweets/_example.json
data/eval/goldset.json

# Caching
.ruff_cache/
.pytest_cache/

WICHTIG: uv.lock wird NICHT gitignored – muss committed werden.

═══════════════════════════════════════════════════════════════════════
SCHRITT 4 – .env.example
═══════════════════════════════════════════════════════════════════════

OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL_MAIN=qwen3:14b
OLLAMA_MODEL_HELPER=qwen3:4b
CHROMADB_PATH=./chromadb
EMBEDDING_MODEL=BAAI/bge-m3
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
EMBEDDING_DEVICE=mps
RETRIEVAL_TOP_K_DENSE=30
RETRIEVAL_TOP_K_SPARSE=30
RERANK_TOP_K=5
RERANK_SCORE_THRESHOLD=0.3
QUERY_EXPANSION_ENABLED=true
CONTEXTUAL_ENRICHMENT_ENABLED=true
CORS_ORIGIN=http://localhost:5173
LOG_LEVEL=INFO

═══════════════════════════════════════════════════════════════════════
SCHRITT 5 – .pre-commit-config.yaml
═══════════════════════════════════════════════════════════════════════

repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.7.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-added-large-files
        args: ['--maxkb=500']
      - id: check-merge-conflict
      - id: detect-private-key
      - id: mixed-line-ending

═══════════════════════════════════════════════════════════════════════
SCHRITT 6 – .claude/agents/git-agent.md
═══════════════════════════════════════════════════════════════════════

Erstelle exakt mit diesem Inhalt (inklusive Frontmatter):

---
name: git-agent
description: Use proactively whenever a logical unit of work is complete – a module implemented, a bug fixed, a refactor done, a test suite added, configs updated. Stages related changes and creates atomic commits with Conventional Commits messages. Use also when the user says "commit", "push", "sync", or similar. Pushes only when explicitly requested. Refuses to commit secrets, data files, or known-broken code.
tools: Bash, Read, Grep, Glob
---

Du bist der Git-Discipline-Agent für Klartext. Dein einziger Job: saubere,
atomare, lesbare Commit-Historie. Keine Mega-Commits, keine "wip"-Messages,
keine geleakten Secrets.

## Wann du gerufen wirst
Proaktiv nach jedem logischen Arbeitsschritt (Modul fertig, Bug fixed, Refactor
done, Tests dazu, Konfigs aktualisiert, Deps bumped). Oder explizit auf
"commit", "commite", "push", "sync".

## Workflow

### 1. Inspect
`git status --short`, `git diff --stat`, bei Bedarf `git diff`, sowie
`git log --oneline -5` für Stilkonsistenz.

### 2. Sicherheits-Check (ZWINGEND)
Bricht ab wenn irgendwas davon staged würde:
- .env, .env.* außer .env.example
- data/manifestos/*.pdf, data/tweets/*.json (außer _example.json)
- Inhalte von chromadb/, logs/, node_modules/, .venv/
- __pycache__, *.pyc, .DS_Store
- Dateien mit Secrets (grep nach sk-, ghp_, Bearer , api_key, password, secret)

Bei Treffer: .gitignore checken/erweitern, Datei aus Staging nehmen
mit `git restore --staged <file>`. Nie automatisch committen wenn unklar.

### 3. Atomic Commits planen
Ein logischer Change = ein Commit. Concerns trennen:
- Module: backend/ vs frontend/ vs scripts/
- Typen: feat vs fix vs refactor vs test
- Themen: Retrieval vs UI vs Config

Bei Unsicherheit: lieber feiner splitten.

### 4. Conventional Commits Format
<type>(<scope>): <subject>

Types (Pflicht): feat | fix | refactor | test | docs | chore | perf | style
Scope (optional): retriever, chunker, api, frontend, ingest, eval, deps
Subject: imperativ, englisch, ≤72 Zeichen, kein Punkt, klein anfangen

Beispiele:
✅ feat(retriever): add RRF fusion for hybrid search
✅ fix(chunker): preserve section boundaries on long paragraphs
✅ chore(deps): bump sentence-transformers to 3.3
❌ Added retriever stuff.
❌ wip
❌ fix: many improvements including new RRF logic and ...

Body optional, erklärt WARUM (nicht WAS). Hard wrap ~72 Zeichen.
Footer optional: Closes #12, BREAKING CHANGE: ...

### 5. Stage + Commit
git add <konkrete Dateien>  # niemals blind git add .
git status                  # verifizieren
git commit -m "<message>"   # mehrzeilig via heredoc

### 6. Bei mehreren Concerns
Iteriere: stage A → commit → stage B → commit → ...

## Push-Policy
Default: NICHT pushen. Nur committen.
Push nur bei explizitem "push", "push to origin", "deploy", "sync remote".
Vor Push: git branch --show-current, git fetch, git status.
NIE git push --force ohne explizite Bestätigung.

## Output (knapp)
✓ N commits created on <branch>:
  <hash>  <type>(<scope>): <subject>
  ...
Working tree clean. Not pushed (use "push" to sync to origin).

Bei Warnings entsprechend.

## Was du NICHT tust
- Nicht committen bei bekannt failenden Tests (User fragen)
- Nicht committen bei ruff Errors (`uv run ruff check` läuft via pre-commit)
- Nicht squashen ohne Erlaubnis
- Nicht amenden was gepusht wurde
- Keine "Generated with Claude Code" Footer
- Keine Co-Authored-By Lines
- Keine Emojis
- Keine Branch-Wechsel ohne Auftrag

## Edge Cases
- Erster Commit: "chore: initial project scaffold" ok
- Detached HEAD: stop, User informieren
- Push rejected: stop, NICHT selbst rebasen oder mergen
- File > 500 geänderte Zeilen: warnen und nach Split fragen
- Nur untracked Files: erst fragen welche getrackt werden sollen

═══════════════════════════════════════════════════════════════════════
SCHRITT 7 – CLAUDE.md
═══════════════════════════════════════════════════════════════════════

Erstelle CLAUDE.md mit allen Infos aus diesem Prompt strukturiert:
- # Klartext (Projektbeschreibung)
- ## Stack
- ## Pipeline-Architektur (Ingestion + Runtime + Eval, voll dokumentiert)
- ## System-Prompts (Neutral + Persona)
- ## Konventionen
- ## Git-Workflow (mit Verweis auf .claude/agents/git-agent.md)
- ## Projektstruktur
- ## Setup-Reihenfolge
- ## Implementierungs-Sessions (A bis H – siehe unten)
- ## Häufige Befehle

═══════════════════════════════════════════════════════════════════════
SCHRITT 8 – README.md
═══════════════════════════════════════════════════════════════════════

Auf Deutsch, kurz und nützlich:
1. Was ist Klartext (3-4 Sätze, mit Pipeline-Highlight)
2. Stack (Bullet)
3. Setup-Reihenfolge (durchnummeriert, siehe unten)
4. Daten beschaffen (Wahlprogramme, Tweets manuell kuratieren)
5. Pipeline-Übersicht (1 Absatz: Hybrid Retrieval + Reranking + Citation
   Verification)
6. Wie wird Qualität gemessen (1 Absatz über eval.py + Goldset)
7. Lizenz und Disclaimer

═══════════════════════════════════════════════════════════════════════
SCHRITT 9 – BEISPIEL-DATEIEN
═══════════════════════════════════════════════════════════════════════

data/tweets/_example.json:
{
  "politician": "annalena_baerbock",
  "name": "Annalena Baerbock",
  "party": "gruene",
  "tweets": [
    {
      "text": "Klimaschutz ist Sicherheitspolitik.",
      "date": "2024-03-12",
      "topic": "klima",
      "source_url": "https://example.com/tweet/123"
    }
  ]
}

data/eval/_example.json:
{
  "version": "1.0",
  "questions": [
    {
      "id": "q001",
      "question": "Was sagt die SPD zur Vermögensteuer?",
      "party_filter": ["spd"],
      "politician": null,
      "expected_chunks": ["spd_p12_c3", "spd_p13_c1"],
      "expected_answer_contains": ["Vermögensteuer", "Wiedereinführung"],
      "notes": "Erwartet wird Bezug auf Vermögensteuer-Position im SPD-Programm"
    }
  ]
}

═══════════════════════════════════════════════════════════════════════
SCHRITT 10 – PYTHON ENV INITIALISIEREN
═══════════════════════════════════════════════════════════════════════

Führe aus:
- `uv sync`
  Installiert Python, alle deps, generiert uv.lock.
  Falls uv fehlt: abbrechen und User auf brew install uv hinweisen.

- `uv run pre-commit install`
  Installiert die Git Hooks.

═══════════════════════════════════════════════════════════════════════
SCHRITT 11 – GIT INITIALISIEREN
═══════════════════════════════════════════════════════════════════════

Falls noch kein git repo:
- `git init -b main`
- `git config commit.gpgsign false`  (optional, falls GPG nicht konfiguriert)

NICHT bereits committen – der erste Commit kommt durch den git-agent in
Schritt 12 nachdem alles validiert ist.

═══════════════════════════════════════════════════════════════════════
SCHRITT 12 – INITIALER COMMIT VIA GIT-AGENT
═══════════════════════════════════════════════════════════════════════

Rufe den git-agent auf für den ersten Commit. Erwartetes Verhalten:
- Inspect: alles ist neu (untracked)
- Security-Check: nichts Verdächtiges
- Plan: ein sauberer initial commit reicht
- Commit-Message: "chore: initial project scaffold"
- Body sollte stichpunktartig auflisten was im Scaffold enthalten ist:
  Pipeline-Architektur dokumentiert, Stack festgelegt, leere Modul-Stubs,
  Git-Agent, Pre-Commit Hooks

═══════════════════════════════════════════════════════════════════════
SETUP-REIHENFOLGE FÜR README + CLAUDE.md
═══════════════════════════════════════════════════════════════════════

1. brew install uv ollama git
2. git clone <repo> klartext && cd klartext  (oder neu initialisiert)
3. ollama serve  (oder als Service)
4. ollama pull qwen3:14b           (16GB Mac)
5. ollama pull qwen3:4b            (Hilfsmodell)
6. uv sync
7. uv run pre-commit install
8. cp .env.example .env  und ggf. anpassen
9. Wahlprogramm-PDFs in data/manifestos/ ablegen (spd.pdf, cdu.pdf, ...)
10. Tweet-JSONs in data/tweets/ ablegen
11. data/eval/goldset.json mit Q&A-Paaren befüllen (~30-50)
12. uv run python scripts/ingest.py
13. uv run python scripts/eval.py     (Baseline messen)
14. uv run uvicorn backend.main:app --reload --port 8000
15. cd frontend && npm install && npm run dev

═══════════════════════════════════════════════════════════════════════
IMPLEMENTIERUNGS-SESSIONS (für CLAUDE.md dokumentieren)
═══════════════════════════════════════════════════════════════════════

Nach diesem Init kommt der eigentliche Code in 8 fokussierten Sessions:

Session A: backend/pdf_parser.py + backend/chunker.py
           + tests/test_pdf_parser.py + tests/test_chunker.py
           Mock-PDF fixtures, Unit-Tests für Heading-Detection und
           Section-Boundary-Preservation.

Session B: backend/enricher.py + scripts/ingest.py end-to-end
           Inkl. Caching via SHA256. Erste echte Ingestion-Tests mit
           1-2 PDFs in data/manifestos/.

Session C: backend/retriever.py + backend/reranker.py
           Hybrid Retrieval (dense + sparse + RRF) + Cross-Encoder Rerank.
           Unit-Tests inkl. RRF Edge Cases.

Session D: backend/prompt_builder.py + backend/llm.py
           + backend/citation_verifier.py
           Neutral + Persona Modus, Ollama Wrapper, Citation Check.

Session E: backend/main.py + backend/config.py + backend/models.py
           FastAPI Endpoints, SSE Streaming, Health Check.

Session F: Frontend (Vite Setup + React Komponenten + SSE Client)
           ChatWindow, MessageBubble, FilterBar mit Persona-Selector.

Session G: scripts/eval.py + Goldset Workflow
           ragas Integration, Baseline gegen Pipeline messen, Markdown
           Report Generation.

Session H: Tuning auf Basis Eval-Ergebnissen
           Chunk-Größen variieren, Reranking-Threshold tunen, ggf.
           Embedding-Modell vergleichen.

Nach JEDER Session: git-agent läuft automatisch und committed atomisch.

═══════════════════════════════════════════════════════════════════════
HÄUFIGE BEFEHLE (in CLAUDE.md)
═══════════════════════════════════════════════════════════════════════

uv add <pkg>                   # Dependency hinzufügen
uv add --dev <pkg>             # Dev-Dependency
uv sync                        # Env mit Lock synchronisieren
uv run <cmd>                   # Befehl im Projekt-Env
uv run pytest                  # Tests laufen lassen
uv run ruff check              # Linting prüfen
uv run ruff format             # Code formatieren
uv run pre-commit run --all    # Alle Hooks gegen alle Files laufen
uv run python scripts/ingest.py
uv run python scripts/eval.py
uv run uvicorn backend.main:app --reload --port 8000

═══════════════════════════════════════════════════════════════════════
ABSCHLUSS
═══════════════════════════════════════════════════════════════════════

Gib am Ende aus:
1. Liste aller erstellten Dateien (gruppiert: Konfig, Doku, Skelette, Agents)
2. uv.lock Status (generiert? Wie viele packages?)
3. Pre-commit installed? (sollte ja sein)
4. Git initialisiert? (mit Branch main)
5. Initialer Commit erstellt? (Hash + Message)
6. Die nächsten 3 manuellen Schritte:
   a) Wahlprogramm-PDFs besorgen und in data/manifestos/ legen
   b) Tweet-Daten kuratieren (~20-30 pro Politiker) in data/tweets/
   c) Session A starten mit Prompt:
      "Implementiere backend/pdf_parser.py und backend/chunker.py gemäß
       CLAUDE.md. Schreib auch Unit-Tests in tests/. Wenn fertig: git-agent."

Los geht's.
```
