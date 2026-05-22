# Setup

Schritt-für-Schritt-Installation auf einem Apple-Silicon-Mac.
Vom Klon bis zur ersten Antwort im Browser.

---

## Voraussetzungen

- **macOS auf Apple Silicon** (M1/M2/M3/M4) — MLX läuft nur dort.
- **16 GB RAM** als Untergrenze. Bei 8 GB Modell-Wechsel zu kleineren
  Quants nötig.
- **~10 GB freier Disk** für Modelle (BGE-M3 ~1.2 GB, Cross-Encoder
  ~0.6 GB, qwen3.5:2b-mlx ~3 GB, ChromaDB-Index pro Manifesto ~50 MB).
- **`brew`** für die Tooling-Installation.

---

## 1. Tooling installieren

```bash
brew install uv ollama git
```

`uv` für Python-Env (alles wird `uv sync` machen), `ollama` für den
LLM-Runner inkl. nativer MLX-Engine.

---

## 2. Repo klonen + Python-Env aufbauen

```bash
git clone git@github.com:jannisg0/klartext.git
cd klartext
uv sync                  # erstellt .venv, installiert mlx-lm, FlagEmbedding, etc.
uv run pre-commit install
```

`uv sync` zieht `mlx-lm`, `mlx-embeddings`, `FlagEmbedding`, ChromaDB,
FastAPI, ragas + alle Test-Deps in ~1 min.

---

## 3. Ollama starten + Modell pullen

```bash
ollama serve   # läuft im Hintergrund; oder einmalig manuell starten
ollama pull qwen3.5:2b-mlx          # Default-Modell, ~3 GB
ollama pull qwen3:14b               # optional, Escape-Hatch
```

Andere brauchbare MLX-Tags: `gemma4:e4b-mlx` (~9.6 GB, langsamer aber
besser bei komplexen Fragen), `qwen3.5:0.8b-mlx` (~1.2 GB, sehr
schnell, schwächere Citation-Discipline).

---

## 4. Environment-Konfiguration

```bash
cp .env.example .env
```

Wichtigste Knobs (komplette Liste in `.env.example`):

| Variable | Default | Zweck |
|----------|---------|-------|
| `LLM_BACKEND` | `ollama` | `ollama` (MLX-Runner) oder `mlx` (direkt mlx-lm) |
| `OLLAMA_MODEL_MAIN` | `qwen3.5:2b-mlx` | Antwort-LLM |
| `OLLAMA_MODEL_HELPER` | `qwen3.5:2b-mlx` | Enrichment + Query-Expansion |
| `RERANK_TOP_K` | `3` | Chunks im LLM-Prompt |
| `RERANK_SCORE_THRESHOLD` | `0.2` | Mindestrelevanz (0..1) |
| `QUERY_EXPANSION_ENABLED` | `false` | Alt-Formulierungen via Helper-LLM |
| `CONTEXTUAL_ENRICHMENT_ENABLED` | `true` | 1 Kontext-Satz pro Chunk beim Ingest |
| `CORS_ORIGIN` | `http://localhost:5173` | Vite-Dev-Server |

---

## 5. Daten einlesen

Wahlprogramme als PDFs in `data/manifestos/<party>.pdf` ablegen:

```
data/manifestos/
  spd.pdf
  cdu.pdf
  diegrünen.pdf
  dielinke.pdf
  fdp.pdf
  afd.pdf
```

Der Dateiname (lowercased) wird zum `party`-Slug; `spd.pdf` → Chunks
`spd_p1_c0`, `spd_p1_c1`, …

Optional: Tweets in `data/tweets/<politician>.json` (Format siehe
`data/tweets/_example.json`). Für Persona-Modus relevant.

Optional: Eval-Goldset in `data/eval/goldset.json` (Format siehe
`_example.json`) — Session G.

```bash
uv run python -m scripts.ingest
```

Erster Lauf:
- BGE-M3 wird von HF geladen (~1.2 GB, einmalig).
- Pro Chunk ein Helper-LLM-Call für Enrichment (bei 60 Chunks SPD ~5 min).
- Schreibt `chromadb/chroma.sqlite3`, `chromadb/bm25_index.pkl`,
  `chromadb/enrichment_cache.json`.

Folgeläufe nutzen den Cache → neue Chunks dauern ~1 s, bekannte
sofort.

---

## 6. Backend starten

```bash
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Erster Start läd Cross-Encoder (Fallback auf sentence-transformers,
~0.6 GB). Health-Check:

```bash
curl -s http://127.0.0.1:8000/health
# {"status":"ok","ollama":true,"chromadb":true,"bm25":true,"chunks":62}
```

Smoke-Test:

```bash
curl -N -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"Was sagt die SPD zur Bildungspolitik?","party_filter":["spd"]}' \
  --max-time 60
```

Erwartete Reihenfolge: `sources` → `token`+ → `citations` → `done`.

---

## 7. Frontend starten

```bash
cd frontend
npm install
npm run dev        # bindet :5173 (strict)
```

`http://localhost:5173/` im Browser. Erste Frage stellen, Sources-
Panel rechts füllt sich, Tokens streamen, Citations als Pillen unter
der Antwort. Detail siehe [`FRONTEND.md`](FRONTEND.md).

---

## 8. Tests + Linting

```bash
uv run pytest -q              # 98 grün
uv run ruff check
uv run ruff format --check
```

Frontend:

```bash
cd frontend && npm run lint && npm run build
```

---

## Häufige Stolpersteine

Siehe [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).
