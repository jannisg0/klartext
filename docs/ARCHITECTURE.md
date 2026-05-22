# Architektur

Klartext ist eine **Retrieval-Augmented-Generation-Pipeline** für deutsche
Wahlprogramme. Alles läuft lokal auf Apple Silicon, Antworten tragen ihre
Quellenangaben mit, jede Aussage wird gegen die retrieved Chunks
verifiziert.

---

## Pipeline auf einen Blick

```
                  ┌─────────────────────────────────────────────────────────┐
INGESTION         │                                                         │
(einmalig)        │  PDFs  ──►  Parser   ──►  Chunker   ──►  Enricher       │
                  │  📄        (PyMuPDF)     (500 tok,       (Helper-LLM:   │
                  │                          overlap=100,    1 Satz pro     │
                  │                          section-aware)  Chunk, SHA256- │
                  │                                          cache)         │
                  │                              │                          │
                  │                              ▼                          │
                  │                          Embedder (BGE-M3)              │
                  │                              │                          │
                  │                              ▼                          │
                  │           ┌──────────────────┴───────────────────┐      │
                  │           ▼                                      ▼      │
                  │      ChromaDB                              BM25-Index   │
                  │   (dense vectors)                      (rank_bm25.pkl)  │
                  └─────────────────────────────────────────────────────────┘

                  ┌─────────────────────────────────────────────────────────┐
RUNTIME           │  User-Query                                             │
(pro Frage)       │     │                                                   │
                  │     ▼                                                   │
                  │  Query Expansion (optional, off by default)             │
                  │     │                                                   │
                  │     ▼                                                   │
                  │  Hybrid Retrieval:  Dense (BGE-M3 + Chroma)  ◄──┐       │
                  │                     Sparse (BM25)              │       │
                  │     │                                          │       │
                  │     ▼                                          │       │
                  │  RRF-Fusion  ──►  Cross-Encoder Rerank  ──►  Top-K     │
                  │                                                │       │
                  │     ┌──────────────────────────────────────────┘       │
                  │     ▼                                                  │
                  │  Prompt-Builder (Neutral / Persona) + Citation-        │
                  │                  Whitelist + Few-Shot                  │
                  │     │                                                  │
                  │     ▼                                                  │
                  │  MLX-LLM-Streaming (qwen3.5:2b-mlx via Ollama-MLX)     │
                  │     │                                                  │
                  │     ▼                                                  │
                  │  Citation Verifier (post-hoc Regex-Check)              │
                  │     │                                                  │
                  │     ▼                                                  │
                  │  SSE-Stream:  sources → token+ → citations → done      │
                  └────────────────────────────────────────────────────────┘
```

---

## Module-Map

| Modul | Pfad | Aufgabe |
|-------|------|---------|
| **PDF-Parser** | `backend/pdf_parser.py` | PyMuPDF, Heading-Detection (Top-3 Fontsizes) |
| **Chunker** | `backend/chunker.py` | Section-aware Chunking, 500 tokens, overlap 100 |
| **Enricher** | `backend/enricher.py` | Contextual Enrichment via Helper-LLM, SHA256-Cache |
| **BM25-Index** | `backend/bm25_index.py` | Sparse-Index, Pickle-Persistenz |
| **Retriever** | `backend/retriever.py` | Hybrid Retrieval (dense + sparse + RRF), party-Filter, Query-Expansion |
| **Reranker** | `backend/reranker.py` | Cross-Encoder + Threshold-Cutoff, leeres-Ergebnis-Signal |
| **Prompt-Builder** | `backend/prompt_builder.py` | Neutral + Persona, Citation-Whitelist + Few-Shot |
| **LLM** | `backend/llm.py` | `MlxLLM` + `OllamaLLM` (Escape Hatch), Streaming-Chat |
| **Citation-Verifier** | `backend/citation_verifier.py` | Regex-Extraction + Verify gegen retrieved Hits |
| **Config** | `backend/config.py` | Pydantic-Settings, alle Knobs aus `.env` |
| **API** | `backend/main.py` | FastAPI-App, SSE-`/chat`, Health-Probe, Threadpool-Wrap |

Ingestion-CLI: `scripts/ingest.py`. Eval-CLI: `scripts/eval.py` (Session G, noch Skelett).

---

## Daten- und Kontrollfluss (Runtime)

1. **User stellt Frage** → `POST /chat` mit `ChatRequest`
   (`query`, `party_filter?`, `politician?`, `history[]`).
2. **`backend/main.py:_stream_chat`** läuft als async-Generator.
   Jeder synchrone Modell-Call wird via `starlette.concurrency.
   run_in_threadpool` ausgelagert, damit der Event-Loop frei bleibt
   und `/health` während Inferenz antwortbereit ist.
3. **Query Expansion** ist standardmäßig aus (`QUERY_EXPANSION_
   ENABLED=false`). Wenn an: Helper-LLM generiert 2 Alt-Formulierungen.
4. **Retrieval**: für jede Query embed BGE-M3, query ChromaDB
   (`top_k=30`) + BM25 (`top_k=30`), Filter auf `party_filter`.
5. **RRF-Fusion** poolt alle Listen, Score `1/(60+rank)`, top 30.
6. **Reranker** scort `(query, chunk)`-Paare per Cross-Encoder
   (sentence-transformers Fallback) und filtert nach Threshold
   (`RERANK_SCORE_THRESHOLD=0.2`). Top `RERANK_TOP_K` Hits.
7. **`sources`-Event** wird sofort gesendet (Frontend kann die
   Sources-Panel füllen während das Modell noch lädt).
8. Wenn keine Hits über Threshold: leeres `citations`-Event + `done`
   → Frontend zeigt "keine belastbaren Stellen".
9. **Prompt** wird gebaut (Neutral oder Persona) mit:
   - Strikten Regeln
   - **Citation Whitelist** (nur retrieved Pages erlaubt — verhindert
     Page-Leak aus Few-Shot-Beispielen)
   - Retrieved Chunks mit `[PARTEI – Seite X]` Vorspann
10. **Streaming via MLX-LLM** (`ollama.chat(..., stream=True, think=
    False)`). `think=False` deaktiviert internen Chain-of-Thought —
    sonst denkt das Modell vor jedem Token ~150 s.
11. Jedes Token → `token`-Event über SSE.
12. **Citation Verifier** parsed nach `done`: Regex
    `[(PARTEI) – Seite (N)]` aus der Antwort, prüft gegen
    retrieved (party, page)-Set. Verified vs unverified.
13. `citations`-Event mit beiden Listen. Frontend hebt
    unverifizierte Citations als gestrichelte Pille hervor.
14. `done`-Event schließt den Stream.

---

## Eigenschaften

- **Local-first**: keine API-Keys, keine externen Calls (außer
  HuggingFace-Modell-Downloads beim ersten Start).
- **Streaming-first**: SSE liefert Sources sofort, Tokens während sie
  generiert werden, Citations ans Ende.
- **Faithfulness by Design**: Citation-Whitelist im Prompt + Post-hoc
  Verifier — Halluzinationen werden im UI als unverifiziert markiert.
- **Backend-agnostic**: `LLM_BACKEND=mlx|ollama` Schalter. Default
  MLX-Pfad nutzt Ollama-MLX-Runner (`gemma4:e4b-mlx`,
  `qwen3.5:2b-mlx`, …); Ollama-Escape-Hatch (`qwen3:14b`) bleibt für
  A/B-Vergleiche.

Siehe [`PIPELINE.md`](PIPELINE.md) für jede Stufe im Detail und
[`DESIGN-DECISIONS.md`](DESIGN-DECISIONS.md) für die Trade-Offs hinter
den oben getroffenen Entscheidungen.
