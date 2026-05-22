# Pipeline-Details

Quelle der Architektur-Übersicht: [`ARCHITECTURE.md`](ARCHITECTURE.md).
Hier: jede Stufe im Detail mit Default-Werten und Implementierungs-
Verweisen.

---

## Ingestion

**CLI:** `uv run python -m scripts.ingest`
**Input:** PDFs in `data/manifestos/<party>.pdf`, JSON-Tweets in
`data/tweets/<politician>.json` (außer `_example.json`).
**Output:** `chromadb/chroma.sqlite3` + `chromadb/bm25_index.pkl` +
`chromadb/enrichment_cache.json`.

### 1. PDF-Parsing — `backend/pdf_parser.py`

PyMuPDF liefert eine TextBlock-Liste mit `(text, fontsize, page,
bbox)`. `detect_heading_sizes()` ermittelt die drei häufigsten
Fontsizes als H1/H2/H3 — eine kleine `tolerance`-Bucket dämpft
Anti-Aliasing-Rauschen. `classify_blocks()` taggt jeden Block mit
`heading_level ∈ {0,1,2,3}`.

### 2. Chunking — `backend/chunker.py`

`chunk_document(blocks, chunk_size=500, overlap=100,
tokenize=None)`:
- Baut hierarchische `section_path`-Strings ("Wirtschaft >
  Steuerpolitik > Vermögensteuer").
- Splittet Body-Text in `chunk_size`-Token-Fenster mit
  `overlap` Token Überlapp.
- **Bricht niemals über Section-Grenzen.**
- Pro Seite eigener `chunk_idx`-Counter → idempotente IDs
  `{party}_p{page}_c{idx}`.

Tokenizer wird injiziert (Default Whitespace-Split; Produktion
nutzt BGE-M3 oder tiktoken).

### 3. Contextual Enrichment — `backend/enricher.py`

Anthropic-Methode: pro Chunk ein Satz vom Helper-LLM, der erklärt
wo der Chunk im Programm sitzt. Wird vor den Chunk-Text geklebt
und mit eingebettet.

Cache-Key: `SHA256(section_path + text)` → JSON-Datei.
**Content-basiert**, also überlebt Modell-Wechsel: wer den Helper
austauscht, behält bestehende Enrichments. Nur neue Chunks
bekommen Sätze vom neuen Modell.

Toggle: `CONTEXTUAL_ENRICHMENT_ENABLED=true|false`.

### 4. Embedding — BGE-M3 via FlagEmbedding

`BAAI/bge-m3` läuft auf MPS (`EMBEDDING_DEVICE=mps`). Liefert
dense Vektoren (1024-dim) für ChromaDB. Sparse-Output wird
**nicht** verwendet — Sparse-Pfad nutzt BM25 stattdessen.

### 5. BM25-Persistenz — `backend/bm25_index.py`

`Bm25Index.build({chunk_id: text})` baut `rank_bm25.BM25Okapi` mit
Unicode-aware `\w+`-Tokenizer (lowercase). `save()`/`load()` als
Pickle.

### 6. ChromaDB-Write

Collection: `klartext_manifestos`. Metadaten pro Chunk:
`{party, section_path, page, chunk_id, context, source_pdf}`.

Tweets analog ohne Chunking → Collection `klartext_tweets`.

---

## Runtime

**Endpoint:** `POST /chat` (siehe [`API.md`](API.md)).
**Orchestrator:** `backend/main.py:_stream_chat` (async-Generator).

### 1. Query Expansion (optional) — `backend/retriever.py:expand_query`

Helper-LLM-Call (qwen3.5:2b-mlx) für 2 Alt-Formulierungen.
Toggle: `QUERY_EXPANSION_ENABLED`. Default `false` weil der
zusätzliche LLM-Call ~5–30 s kostet.

### 2. Hybrid Retrieval — `backend/retriever.py:HybridRetriever.retrieve`

Pro Query:
- **Dense**: `BGE-M3.encode(query)` → `collection.query(top_k=30,
  where={'party': {'$in': party_filter}})`.
- **Sparse**: `bm25.search(query, top_k=30)`, post-Filter über
  ID-Prefix (`spd_*`, `cdu_*`, …) für party-Filter.

Defaults: `RETRIEVAL_TOP_K_DENSE=30`, `RETRIEVAL_TOP_K_SPARSE=30`.

### 3. RRF-Fusion — `backend/retriever.py:rrf_fuse`

Reciprocal Rank Fusion mit `k=60`:
`score(id) = Σ 1 / (60 + rank_in_list)`.
Pool aller Listen, sortiert absteigend nach Score, top 30 keepen.

### 4. Cross-Encoder Rerank — `backend/reranker.py`

Default: `mlx-community/bge-reranker-v2-m3-4bit` via
`mlx-embeddings` (falls verfügbar) ODER `BAAI/bge-reranker-v2-m3`
via `sentence-transformers` (Fallback).

`CrossEncoderReranker.rerank(query, hits, top_k=3)`:
- Score-Sigmoid auf `[0, 1]`.
- Drop Hits mit Score < `RERANK_SCORE_THRESHOLD` (default `0.2`).
- Wenn Top-Hit < Threshold → `below_threshold=True` Signal.
- `top_k=3` ist tuned auf small-LLM-Prompt-Budget (ehemals 5,
  reduziert weil 2B-Modelle bei großem Prompt langsam werden).

### 5. Prompt-Konstruktion — `backend/prompt_builder.py`

`build_neutral_prompt(query, hits, history?)` →
`list[Message]`. Inhalt:
- Hartes Citation-Regelwerk (siehe `_NEUTRAL_SYSTEM`).
- **Citation Whitelist** (`build_citation_whitelist(hits)`): genau
  die `[PARTEI – Seite N]`-Strings der retrieved Hits, eingebaut in
  den System-Prompt. Verhindert dass das Modell Page-Nummern aus
  Few-Shot-Beispielen halluziniert.
- Few-Shot-Beispiele im Mindestlohn- / Vermögensteuer-Stil.
- Retrieved Chunks als Block.

Persona-Variante: zusätzlicher Overlay mit Tweets als Tonal-Reference
+ Pflicht-Footer `[Stil-Imitation – keine echten Zitate]`.

Conversation-History wird auf `MAX_HISTORY=10` Messages gekappt.

### 6. LLM-Streaming — `backend/llm.py`

`OllamaLLM.chat_stream(messages)`:
- `ollama.chat(stream=True, think=False, options={temperature,
  num_ctx})`.
- **`think=False` ist kritisch**: Thinking-fähige Modelle (gemma4,
  qwen3) verbrennen sonst 30–150 s im internen CoT vor dem ersten
  Token.

Yielded werden nur nicht-leere `chunk.message.content`-Strings;
Sentinel `chunk.done` terminiert.

MLX-Pfad (`MlxLLM`) nutzt `mlx_lm.stream_generate` direkt — derzeit
durch Ollama-MLX-Runner ersetzt weil Ollama Multi-Modal-Modelle
(z.B. `gemma4:e4b-mlx`) lädt, die `mlx_lm.load` nicht parst.

### 7. Citation Verification — `backend/citation_verifier.py`

Nach `done` (Server-side, vor `citations`-Event):
- Regex `\[(\w+)\s*[–—-]\s*Seite\s+(\d+)\]` extrahiert alle
  Citations aus der Antwort.
- Vergleich gegen `{(party.lower(), page): hit}` aus retrieved Hits.
- Dedupliziert.
- Ausgabe: `VerificationResult(verified=[...], unverified=[...])`.

### 8. SSE-Stream-Reihenfolge

```
event: sources       data: [SourceItem, ...]
event: token         data: {"text": "..."}  (n mal)
event: citations     data: {"verified": [...], "unverified": [...]}
event: done          data: {}
```

Bei `below_threshold`: `sources` (möglicherweise leer) →
`citations` (leer) → `done`. **Keine** token-Events.

Bei Backend-Fehler: einzelnes `error`-Event mit `{message}`.

Frontend-SSE-Contract identisch in
[`API.md`](API.md) + [`FRONTEND.md`](FRONTEND.md).
