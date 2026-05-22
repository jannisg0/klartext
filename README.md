# Klartext

Klartext ist ein lokaler politischer RAG-Chatbot für ein Hochschulprojekt.
Er beantwortet Fragen zu Wahlprogrammen auf Basis verifizierter
Quellenangaben und kann optional im Stil ausgewählter Politiker:innen
antworten. Die Pipeline kombiniert Hybrid Retrieval (Dense + Sparse + RRF),
Cross-Encoder Reranking, Contextual Chunks und post-hoc Citation
Verification. Alles läuft lokal nativ auf Apple Silicon via MLX – keine
Daten verlassen den Rechner.

## Stack

- **Python ≥3.11**, Package Manager: **uv**
- **LLM (MLX)**: `mlx-community/gemma-4-e4b-it-OptiQ-4bit`
  (Haupt + Hilfs – ein Gewichtssatz, beide Rollen). Per
  `LLM_BACKEND=ollama` lässt sich der alte Ollama-Pfad (`qwen3:14b` /
  `qwen3:4b`) für A/B-Vergleiche reaktivieren.
- **Embeddings**: `BAAI/bge-m3` via FlagEmbedding (dense + sparse)
- **Reranker**: `mlx-community/bge-reranker-v2-m3-4bit` (MLX), Fallback
  auf `BAAI/bge-reranker-v2-m3` via sentence-transformers
- **Vector DB**: ChromaDB (lokal, persistiert)
- **Sparse Index**: `rank_bm25`
- **PDF-Parsing**: PyMuPDF
- **Backend**: FastAPI + Server-Sent Events
- **Frontend**: React (Vite) + Tailwind
- **Eval**: ragas + manuell kuratiertes Goldset
- **Linting**: ruff via pre-commit
- **Logging**: structlog (JSON)

## Setup

1. `brew install uv git` (Apple Silicon Mac vorausgesetzt)
2. `uv sync` (lädt mlx-lm + FlagEmbedding etc.)
3. `uv run pre-commit install`
4. `cp .env.example .env` und ggf. anpassen
5. Wahlprogramm-PDFs in `data/manifestos/` ablegen (z.B. `spd.pdf`, `cdu.pdf`, ...)
6. Tweet-JSONs in `data/tweets/` ablegen (Format: siehe `_example.json`)
7. `data/eval/goldset.json` mit Q&A-Paaren befüllen (~30-50)
8. `uv run python scripts/ingest.py` (erster Lauf zieht das MLX-Modell
   von HuggingFace, ~5 GB; danach gecached)
9. `uv run python scripts/eval.py` (Baseline messen)
10. `uv run uvicorn backend.main:app --reload --port 8000`
11. `cd frontend && npm install && npm run dev`

Wer den Ollama-Pfad bevorzugt: `LLM_BACKEND=ollama` setzen, `ollama serve`
laufen lassen und `ollama pull qwen3:14b qwen3:4b`.

## Daten beschaffen

- **Wahlprogramme**: Offizielle PDFs der Parteien (Bundestagswahl, Landtagswahlen).
  In `data/manifestos/` als `<party>.pdf` ablegen (`spd.pdf`, `cdu.pdf`, etc.).
- **Tweets**: Manuell kuratierte JSON-Sammlung pro Politiker:in (~20-30 Tweets,
  Format siehe `data/tweets/_example.json`). Realtime-Scraping ist NICHT
  Bestandteil des Projekts – Fokus liegt auf reproduzierbarer Qualität.
- **Goldset**: Eval-Fragen mit erwarteten Quellen und Antwort-Substrings
  manuell schreiben (`data/eval/goldset.json`), Format siehe `_example.json`.

## Pipeline-Übersicht

Bei jeder Frage werden zunächst alternative Formulierungen via dem
Helper-Modell (MLX Gemma 4 E4B, oder Ollama-Helper im Escape-Hatch)
generiert, dann parallel **Dense** (BGE-M3 + ChromaDB) und **Sparse** (BM25)
Retrieval durchgeführt. Die Ergebnislisten werden via **Reciprocal Rank
Fusion** kombiniert und durch einen **Cross-Encoder Reranker** auf die Top 5
Chunks reduziert. Das LLM bekommt nur diese Top-Chunks plus strikte
Citation-Regeln. Nach der Generation prüft ein **Citation Verifier** per
Regex, dass jede `[PARTEI – Seite X]`-Referenz tatsächlich aus dem
Kontext stammt – unverifizierte Citations werden als Warning im SSE-Stream
markiert.

## Qualität messen

`scripts/eval.py` führt das komplette System gegen das Goldset aus und
berechnet ragas-Metriken: `context_precision`, `context_recall`,
`faithfulness`, `answer_relevance`. Ergebnis landet als JSON + Markdown-
Summary in `logs/`. Diese Baseline ist die Referenz für Tuning-Entscheidungen
(Chunk-Größe, Reranking-Threshold, Embedding-Modell).

## Lizenz und Disclaimer

Hochschulprojekt zu Demonstrations- und Lehrzwecken. **Keine offizielle
Wiedergabe** politischer Positionen. Im Persona-Modus erzeugt das System
explizit **Stil-Imitationen** – keine echten Zitate der genannten Personen.
Antworten können trotz Citation Verification fehlerhaft sein; immer gegen
die Originalprogramme prüfen.
