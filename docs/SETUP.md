# Setup

Schritt-für-Schritt-Installation auf einem Apple-Silicon-Mac.
Vom Klon bis zur ersten Antwort im Browser.

---

## Voraussetzungen

- **macOS auf Apple Silicon** (M1/M2/M3/M4) — MLX läuft nur dort.
- **16 GB RAM** als Untergrenze. Bei 8 GB Modell-Wechsel zu kleineren
  Quants nötig.
- **~5 GB freier Disk** für Modelle (BGE-M3 MLX ~1.2 GB,
  Qwen3.5-2B-4bit ~2 GB, ChromaDB-Index pro Manifesto ~50 MB).
- **`brew`** für die Tooling-Installation.

---

## 1. Tooling installieren

```bash
brew install uv git
```

`uv` für Python-Env. `mlx-lm` wird via `uv sync` aus `pyproject.toml`
installiert — kein separater Tool-Manager nötig.

---

## 2. Repo klonen + Python-Env aufbauen

```bash
git clone git@github.com:jannisg0/klartext.git
cd klartext
uv sync                  # erstellt .venv, installiert mlx-lm, mlx-embeddings, openai, etc.
uv run pre-commit install
```

`uv sync` zieht `mlx-lm`, `mlx-embeddings`, `openai`, ChromaDB,
FastAPI, ragas + alle Test-Deps in ~1 min.

---

## 3. MLX-LLM-Server starten

```bash
uv run mlx_lm.server --model mlx-community/Qwen3.5-2B-OptiQ-4bit --port 8000
```

Erster Start lädt das Modell von HuggingFace (~2 GB, einmalig in HF-Cache).
Server läuft dann auf `:8000/v1` (OpenAI-kompatibler Endpunkt).

**Escape-Hatch (Ollama):** Wer stattdessen Ollama nutzen will:
```bash
brew install ollama && ollama serve
ollama pull qwen3:14b
# in .env: LLM_BACKEND=ollama, OLLAMA_MODEL_MAIN=qwen3:14b
```

---

## 4. Environment-Konfiguration

```bash
cp .env.example .env
```

Wichtigste Knobs (komplette Liste in `.env.example`):

| Variable | Default | Zweck |
|----------|---------|-------|
| `LLM_BACKEND` | `mlx` | `mlx` → mlx-lm Server auf `OMLX_BASE_URL`; `ollama` → Ollama OpenAI-Gateway |
| `OMLX_MODEL` | `mlx-community/Qwen3.5-2B-OptiQ-4bit` | Modell-ID für mlx-lm Server |
| `OLLAMA_MODEL_MAIN` | `qwen3:14b` | Antwort-LLM (Escape-Hatch) |
| `OLLAMA_MODEL_HELPER` | `qwen3:4b` | Enrichment + Query-Expansion (Escape-Hatch) |
| `RERANK_TOP_K` | `5` | Chunks im LLM-Prompt |
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
- BGE-M3 (`bge-m3-mlx-8bit`) wird von HF geladen (~1.2 GB, einmalig).
- Pro Chunk ein Helper-LLM-Call für Enrichment (bei 63 Chunks ~5 min).
- Schreibt `chromadb/chroma.sqlite3`, `chromadb/bm25_index.pkl`,
  `chromadb/enrichment_cache.json`.

Folgeläufe nutzen den Cache → neue Chunks dauern ~1 s, bekannte
sofort.

---

## 6. Backend starten

```bash
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8001 --reload
```

Health-Check:

```bash
curl -s http://127.0.0.1:8001/health
# {"status":"ok","ollama":true,"chromadb":true,"bm25":true,"chunks":62}
```

Smoke-Test:

```bash
curl -N -s -X POST http://127.0.0.1:8001/chat \
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
uv run pytest -q              # 112 grün
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
