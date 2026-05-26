# Klartext

Lokaler politischer RAG-Chatbot für ein Hochschulprojekt. Beantwortet Fragen
zu Wahlprogrammen auf Basis verifizierter Quellenangaben, optional im Stil
gewählter Politiker:innen (Persona-Modus). Der Name verpflichtet: klare
Sprache, verifizierte Zitate, keine Halluzinationen.

Ziel ist Pipeline-Qualität auf professionellem Niveau – Hybrid Retrieval,
Log-Prob Reranking, Contextual Chunks, ragas-basierte Evaluation.

---

## Stack

- **Package Manager**: uv (pyproject.toml + uv.lock)
- **Python**: >=3.11
- **LLM (MLX, default)**: `mlx-community/gemma-4-e4b-it-OptiQ-4bit` via
  `mlx-lm --server` (OpenAI-kompatibler Inference-Server auf `:8000`).
  Ein Gewichtssatz für Answer-Generation und Helper-Rolle.
- **LLM (Ollama, Escape Hatch)**: `LLM_BACKEND=ollama` — beide Pfade
  nutzen die OpenAI-SDK gegen den jeweiligen Endpunkt (`/v1`).
- **Embeddings**: `mlx-community/bge-m3-mlx-8bit` via mlx-embeddings
- **Reranker**: Log-Prob-Reranker via Chat Completions — kein separates
  Reranker-Modell, nutzt denselben Inference-Server.
- **Vector DB**: ChromaDB (lokal, persistiert)
- **Sparse Index**: rank_bm25 (in-memory, persistiert als pickle)
- **PDF-Parsing**: PyMuPDF (layout-aware mit Heading-Detection)
- **Eval**: ragas + manuell kuratiertes Goldset
- **Backend**: FastAPI + Server-Sent Events
- **Frontend**: React (Vite) + Tailwind, dunkles Theme, kein TypeScript
- **Linting**: ruff (lint + format) via pre-commit
- **Logging**: structlog (strukturierte Logs für Eval)
- **Git-Discipline**: dedizierter Subagent (`.claude/agents/git-agent.md`)

---

## Pipeline-Architektur

### Ingestion (einmalig pro Datenupdate)

1. **pymupdf4llm** parst PDF zu strukturiertem Markdown (Headings, Listen,
   Tabellen) — keine Fontsize-Heuristik.
2. **Markdown-aware Chunking**:
   - `chunk_size=500` tokens, `overlap=100`
   - NIE über Sektionsgrenzen chunken
   - `section_path` als Metadatum: `"Wirtschaft > Steuerpolitik > Vermögensteuer"`
3. **Contextual Enrichment** (Anthropic-Methode):
   - Pro Chunk Call an das Helper-LLM (OpenAI SDK gegen mlx-lm Server
     oder Ollama `/v1` im Escape-Hatch):
     ```
     Document-Kontext: {section_path}
     Chunk: {chunk}
     Schreibe EINEN Satz der erklärt wo dieser Chunk im Wahlprogramm sitzt.
     Nur den Satz, sonst nichts.
     ```
   - Generierten Satz vor den Chunk kleben.
   - Caching: SHA256 von `(section_path, text)` als Key — rein
     content-basiert. Ein Modellwechsel invalidiert den Cache **nicht**;
     bestehende Enrichments bleiben, neue Chunks bekommen die Sätze vom
     aktuell aktiven Helper-Modell.
4. **Embedding mit BGE-M3** (mlx-embeddings, `bge-m3-mlx-8bit`):
   - dense vector → ChromaDB Collection `klartext_manifestos`
   - sparse weights → BM25 Index (Term-Frequencies)
5. **Metadaten**: `{party, section_path, page, chunk_id, context, source_pdf}`.
6. **Tweets analog** ohne Chunking → Collection `klartext_tweets`.

### Runtime (pro User-Query)

1. Query empfangen + Filter (`party_filter`, `politician`).
2. **Query Expansion** via Helper-LLM (toggelbar):
   ```
   Generiere 2 alternative deutsche Formulierungen dieser Frage.
   ```
   → 3 Queries total.
3. **Hybrid Retrieval** (für JEDE Query):
   - a) Dense via BGE-M3 + ChromaDB → top 30
   - b) Sparse via rank_bm25 → top 30
4. **RRF Fusion**: alle Listen poolen, Score `1/(60+rank)` summieren, top 30 keepen.
5. **Log-Prob Reranking** via Chat Completions (kein separates Modell):
   - Pro Hit: LLM antwortet „Ja/Nein" auf Relevanzfrage
   - Log-Prob des „Ja"-Tokens = Relevanz-Score
   - Top 5 keepen, Score < threshold (default `0.2`) → leeres Ergebnis
6. **Prompt-Konstruktion** (siehe System-Prompts unten).
7. **LLM-Generation** via OpenAI SDK (`chat_stream`), streaming.
8. **Citation Verification post-hoc**:
   - Regex `\[(\w+) – Seite (\d+)\]` aus Antwort extrahieren
   - Jede gegen retrieved chunks prüfen
   - Unverifizierte → Warning event im SSE-Stream
9. **SSE-Stream-Reihenfolge**:
   - `sources` event (Top 5 mit scores)
   - `token` events (LLM stream)
   - `citations` event (verified / unverified Liste)
   - `done` event

### Evaluation

`data/eval/goldset.json` mit ~30-50 manuell kuratierten Q&A-Paaren:

```json
{
  "question": "Was sagt die SPD zur Vermögensteuer?",
  "party_filter": ["spd"],
  "expected_chunks": ["spd_p12_c3", "spd_p13_c1"],
  "expected_answer_contains": ["Vermögensteuer", "Wiedereinführung"]
}
```

`scripts/eval.py`:
- Lädt Goldset
- Führt komplette Pipeline pro Frage aus
- Berechnet ragas Metriken: `context_precision`, `context_recall`,
  `faithfulness`, `answer_relevance`
- Ausgabe: `logs/eval_{timestamp}.json` + Markdown-Summary

---

## System-Prompts

### Neutral-Modus

```
Du bist Klartext, ein politischer RAG-Assistent. Antworte AUSSCHLIESSLICH
auf Basis der bereitgestellten Wahlprogramm-Auszüge. Regeln:
- Jede Aussage mit [PARTEI – Seite X] zitieren
- Erfinde keine Zitate, keine Fakten, keine Zahlen
- Wenn der Kontext die Frage nicht beantwortet, sage das KLAR
- Wenn mehrere Parteien unterschiedliche Positionen haben, stelle sie
  gleichwertig nebeneinander
- Vermeide Wertungen wie 'gut', 'schlecht', 'sinnvoll'
Kontext: {chunks_with_citations}
```

### Persona-Modus (zusätzlich)

```
Du sprichst im Stil von {politician_name}. Stilreferenz (NUR Tonfall,
NICHT Inhalt erfinden): {tweets}
Beende die Antwort mit: [Stil-Imitation – keine echten Zitate]
```

---

## Konventionen

- Code, Variablen, Logging: **Englisch**
- User-facing Strings, Prompts: **Deutsch**
- Idempotente IDs:
  - Chunks: `{party}_{page}_{chunk_idx}` (z.B. `spd_p12_c3`)
  - Tweets: `{politician}_{idx}`
- ChromaDB Collections: `klartext_manifestos`, `klartext_tweets`
- BM25 Index: `chromadb/bm25_index.pkl`
- Conversation History: serverseitig max 10 Messages an LLM
- Alle Python-Befehle via `uv run`
- Linting: ruff (`line-length=100`, `target=py311`)
- Tests in `tests/`, ausgeführt via `uv run pytest`
- Logging: structlog mit JSON-Output nach `logs/klartext.log`

---

## Git-Workflow

Ausschließlich über den **git-agent** (siehe `.claude/agents/git-agent.md`).

Der Agent erzwingt:
- Conventional Commits (`feat | fix | refactor | test | docs | chore | perf | style`)
- Atomic Commits (ein logischer Change = ein Commit)
- Sicherheits-Check vor Stage (keine Secrets, keine Daten, keine Artifacts)
- Push nur bei explizitem Auftrag
- Keine "Generated with Claude Code" Footer, keine Co-Authored-By Lines

Nach jeder Implementierungs-Session: git-agent aufrufen.

---

## Projektstruktur

```
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
├── docs/
│   └── design/
│       └── Klartext.html      (Claude-Design Handover, Session F)
├── data/
│   ├── manifestos/         (PDFs, gitignored)
│   ├── tweets/             (JSONs, gitignored außer _example.json)
│   └── eval/               (goldset.json gitignored)
├── scripts/
│   ├── ingest.py           (Session B)
│   └── eval.py             (Session G)
├── backend/
│   ├── main.py             (Session E)
│   ├── config.py           (Session E)
│   ├── models.py           (Session E)
│   ├── pdf_parser.py       (Session A)
│   ├── chunker.py          (Session A)
│   ├── enricher.py         (Session B)
│   ├── retriever.py        (Session C)
│   ├── reranker.py         (Session C)
│   ├── prompt_builder.py   (Session D)
│   ├── llm.py              (Session D)
│   └── citation_verifier.py (Session D)
├── frontend/               (Session F: Vite + React)
├── tests/
├── chromadb/               (Inhalte gitignored)
└── logs/                   (Inhalte gitignored)
```

---

## Setup-Reihenfolge

1. `brew install uv git` (Apple Silicon Mac vorausgesetzt)
2. `git clone <repo> klartext && cd klartext` (oder neu initialisiert)
3. `uv sync` (zieht `mlx-lm`, `mlx-embeddings`, `openai` etc.)
4. `uv run pre-commit install`
5. `cp .env.example .env` und ggf. anpassen
6. Wahlprogramm-PDFs in `data/manifestos/` ablegen (`spd.pdf`, `cdu.pdf`, ...)
7. Tweet-JSONs in `data/tweets/` ablegen
8. `data/eval/goldset.json` mit Q&A-Paaren befüllen (~30-50)
9. `uv run python scripts/ingest.py` (erster Lauf zieht das MLX-Modell
   von HuggingFace, ~5 GB; danach im HF-Cache)
10. `uv run python scripts/eval.py` (Baseline messen)
11. `uv run uvicorn backend.main:app --reload --port 8001`
12. `cd frontend && npm install && npm run dev`

Escape-Hatch: `LLM_BACKEND=ollama` setzen, `ollama serve` starten —
OpenAI SDK zeigt dann auf `OLLAMA_HOST/v1` statt auf den mlx-lm Server.

---

## Implementierungs-Sessions

Nach dem Init kommt der eigentliche Code in 8 fokussierten Sessions:

- **Session A**: `backend/pdf_parser.py` + `backend/chunker.py`
  + `tests/test_pdf_parser.py` + `tests/test_chunker.py`. Mock-PDF
  fixtures, Unit-Tests für Heading-Detection und Section-Boundary-Preservation.
- **Session B**: `backend/enricher.py` + `scripts/ingest.py` end-to-end.
  Inkl. Caching via SHA256. Erste echte Ingestion-Tests mit 1-2 PDFs in
  `data/manifestos/`.
- **Session C**: `backend/retriever.py` + `backend/reranker.py`. Hybrid
  Retrieval (dense + sparse + RRF) + Log-Prob Reranking. Unit-Tests inkl.
  RRF Edge Cases.
- **Session D**: `backend/prompt_builder.py` + `backend/llm.py`
  + `backend/citation_verifier.py`. Neutral + Persona Modus, OpenAI SDK
  Wrapper, Citation Check.
- **Session E**: `backend/main.py` + `backend/config.py` + `backend/models.py`.
  FastAPI Endpoints, SSE Streaming, Health Check.
- **Session F**: Frontend (Vite Setup + React Komponenten + SSE Client).
  ChatWindow, MessageBubble, FilterBar mit Persona-Selector.
- **Session G**: `scripts/eval.py` + Goldset Workflow. ragas Integration,
  Baseline gegen Pipeline messen, Markdown Report Generation.
- **Session H**: Tuning auf Basis Eval-Ergebnissen. Chunk-Größen variieren,
  Reranking-Threshold tunen, ggf. Embedding-Modell vergleichen.

Nach JEDER Session: **git-agent läuft automatisch und committed atomisch**.

---

## Häufige Befehle

```bash
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
uv run uvicorn backend.main:app --reload --port 8001
```
