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
                  Log-Prob Rerank (Ja/Nein via LLM)
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
| LLM (Default) | `mlx-community/Qwen3.5-2B-OptiQ-4bit` via `mlx-lm --server` |
| LLM (Escape Hatch) | `qwen3:14b` via Ollama OpenAI-Gateway (`LLM_BACKEND=ollama`) |
| Embeddings | `mlx-community/bge-m3-mlx-8bit` via `mlx-embeddings` |
| Reranker | Log-Prob (Ja/Nein-Logprobs vom selben LLM, kein extra Modell) |
| Vector DB | ChromaDB (persistent) |
| Sparse | `rank_bm25` |
| Backend | FastAPI + sse-starlette |
| Frontend | Vite + React + Tailwind (kein TS) |
| Eval | `ragas` + manuell kuratiertes Goldset (Session G) |
| Tests | pytest, 112 grün |

Warum dieser Stack: [`docs/DESIGN-DECISIONS.md`](docs/DESIGN-DECISIONS.md).

---

## Quickstart

Voraussetzung: Apple Silicon (M1+), 16 GB RAM, `brew install uv git`.

```bash
git clone git@github.com:jannisg0/klartext.git
cd klartext
uv sync
cp .env.example .env
# MLX-LLM-Server starten (Terminal 1):
uv run mlx_lm.server --model mlx-community/Qwen3.5-2B-OptiQ-4bit --port 8000
# PDFs in data/manifestos/<party>.pdf ablegen, dann ingestieren:
uv run python -m scripts.ingest
# Backend starten (Terminal 2):
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8001
# Frontend starten (Terminal 3):
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
| MLX-Migration | mlx-lm Server + OpenAI SDK als Default | abgeschlossen |
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
