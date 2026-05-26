# Klartext

**Lokaler RAG-Chatbot für deutsche Wahlprogramme, mit verifizierten Quellen.**

Klartext beantwortet politische Fragen ausschließlich auf Basis
der Wahlprogramme im Repository. Jede Aussage trägt ihre Quelle als
`[PARTEI – Seite X]`-Pille bei sich; ein post-hoc Citation-Verifier
markiert hallucinierte Belege rot. Alles läuft lokal auf Apple
Silicon — keine API-Keys, kein Datenabfluss.

Optionaler **Persona-Modus** lässt das Modell im Stil ausgewählter
Politiker:innen antworten, mit explizitem `[Stil-Imitation – keine
echten Zitate]`-Footer.

---

## Wie es funktioniert

```
PDF  →  Parser  →  Chunker  →  Contextual Enrichment  →  Embedding
                                                            │
                            ┌───────────────────────────────┘
                            ▼
                    ChromaDB + BM25-Index
                            │
User-Query  ──►  Hybrid Retrieval (Dense + Sparse + RRF)
                            │
                            ▼
                    Cross-Encoder Rerank
                            │
                            ▼
              Prompt-Builder (mit Citation Whitelist)
                            │
                            ▼
              MLX-LLM streamt Antwort (Server-Sent Events)
                            │
                            ▼
              Citation-Verifier prüft jede [PARTEI – Seite X]
```

Volldetail in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) und
[`docs/PIPELINE.md`](docs/PIPELINE.md).

---

## Stack auf einen Blick

| Schicht | Komponente |
|---------|------------|
| LLM (Default) | `qwen3.5:2b-mlx` via Ollama-MLX-Runner |
| LLM (Escape Hatch) | `qwen3:14b` via Ollama (`LLM_BACKEND=ollama`) |
| Embeddings | `BAAI/bge-m3` via FlagEmbedding (MPS) |
| Reranker | `bge-reranker-v2-m3` via sentence-transformers |
| Vector DB | ChromaDB (persistent) |
| Sparse | `rank_bm25` |
| Backend | FastAPI + sse-starlette |
| Frontend | Vite + React + Tailwind (kein TS) |
| Eval | `ragas` + manuell kuratiertes Goldset (Session G) |
| Tests | pytest, 98 grün |

Warum dieser Stack: [`docs/DESIGN-DECISIONS.md`](docs/DESIGN-DECISIONS.md).

---

## Quickstart

Voraussetzung: Apple Silicon (M1+), 16 GB RAM, `brew install uv ollama git`.

```bash
git clone git@github.com:jannisg0/klartext.git
cd klartext
uv sync
ollama pull qwen3.5:2b-mlx
cp .env.example .env
# PDFs in data/manifestos/<party>.pdf ablegen
uv run python -m scripts.ingest
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8001
# in zweitem Terminal:
cd frontend && npm install && npm run dev
```

Browser auf `http://localhost:5173/`. Volle Anleitung mit
Voraussetzungen + Konfig-Knobs in [`docs/SETUP.md`](docs/SETUP.md).

---

## Status

| Session | Inhalt | Status |
|---------|--------|--------|
| A | PDF-Parser + Chunker | abgeschlossen |
| B | Enricher + Ingestion-CLI | abgeschlossen |
| C | Retriever + Reranker | abgeschlossen |
| D | Prompt-Builder + LLM + Citation-Verifier | abgeschlossen |
| E | FastAPI-App + SSE-Streaming | abgeschlossen |
| F + F2 | Frontend Design-Integration + Backend-Wiring | abgeschlossen |
| MLX-Migration | Ollama-MLX-Runner als Default | abgeschlossen |
| G | Eval-Skript (ragas) + Goldset | offen |
| H | Tuning auf Basis Eval-Ergebnissen | offen |

---

## Dokumentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — Pipeline-Übersicht
- [`docs/PIPELINE.md`](docs/PIPELINE.md) — Ingestion + Runtime im Detail
- [`docs/DESIGN-DECISIONS.md`](docs/DESIGN-DECISIONS.md) — Warum MLX,
  warum Hybrid, warum Citation-Whitelist
- [`docs/SETUP.md`](docs/SETUP.md) — Schritt-für-Schritt-Installation
- [`docs/API.md`](docs/API.md) — `/health` + `/chat` SSE-Contract
- [`docs/FRONTEND.md`](docs/FRONTEND.md) — Komponenten + Dev-Loop
- [`docs/EVALUATION.md`](docs/EVALUATION.md) — Goldset + ragas (Session G)
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — Stolpersteine
- [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) — Code-Stil + Git-Discipline
- [`CLAUDE.md`](CLAUDE.md) — Entwickler- + Agent-Referenz
  (System-Prompts, vollständige Konventionen)

---

## Lizenz und Disclaimer

Hochschulprojekt zu Demonstrations- und Lehrzwecken. **Keine offizielle
Wiedergabe** politischer Positionen. Im Persona-Modus erzeugt das System
explizit Stil-Imitationen — keine echten Zitate der genannten Personen.
Antworten können trotz Citation-Verification fehlerhaft sein; immer
gegen die Originalprogramme prüfen.
