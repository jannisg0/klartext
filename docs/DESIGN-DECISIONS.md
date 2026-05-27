# Design-Entscheidungen

Die Stationen, an denen wir die Architektur gegen einen schmerzhaften
Trade-off entschieden haben. Jeder Eintrag: Problem, Lösung, was wir
aufgegeben haben.

---

## 1. `mlx-lm --server` statt Ollama-MLX-Runner

**Problem:** Ursprünglich Ollama-MLX-Runner (`qwen3.5:2b-mlx` via
`ollama serve`). Vorteil war, dass Ollama VLMs (z. B. `gemma4:e4b-mlx`)
versteht die `mlx-lm` nicht parst. Nachteil: extra Prozess,
`think=False` als Ollama-spezifisches Flag, kein Standard-API-Vertrag.

**Lösung:** `mlx-lm --server` auf `:8000` exponiert einen OpenAI-
kompatiblen Endpunkt. Backend nutzt OpenAI SDK — ein `OpenAILLM`
deckt MLX-Default und Ollama-Escape-Hatch ab (nur `base_url` wechselt).
Thinking-Modus wird via `extra_body={"chat_template_kwargs":
{"enable_thinking": False}}` deaktiviert — derselbe Mechanismus
funktioniert für Qwen3, Gemma und jeden anderen Thinking-fähigen
mlx-lm-Modell.

**Trade-off:** VLMs (`gemma4:e4b`) brauchen Escape-Hatch via Ollama.
Pure LLM-Quants (`Qwen3.5-2B-OptiQ-4bit`) laufen direkt.

---

## 2. `Qwen3.5-2B-OptiQ-4bit` als Default-LLM

**Problem:** `qwen3:14b` (~9 GB) auf 16 GB Mac liefert hochwertige
Antworten, braucht aber 170–300 s Wall-Time — unbenutzbar. Größere
MoE-Modelle qualitativ ähnlich aber selbst mit deaktiviertem Thinking
~30 s TTFB wegen großer Prompt-Eval.

**Lösung:** `mlx-community/Qwen3.5-2B-OptiQ-4bit` (~2 GB) bei ~24 s
Wall-Time, ~14 s TTFB. Citation-Discipline kommt nicht von alleine —
kleinere Modelle ignorieren das `[PARTEI – Seite X]`-Format. Daher
Few-Shot-Beispiele im System-Prompt + explizite Whitelist der erlaubten
Citations (siehe Punkt 4).

**Trade-off:** Antworten knapper als bei 14B-Modellen. Quality-vs-
Speed-Sweet-Spot für interaktiven Chat. `LLM_BACKEND=ollama` +
`OLLAMA_MODEL_MAIN=qwen3:14b` bleibt als A/B-Escape-Hatch.

---

## 3. BGE-M3 via `mlx-embeddings`

**Problem:** `BAAI/bge-m3` via `FlagEmbedding` (PyTorch/MPS) war der
ursprüngliche Pfad — funktioniert, aber PyTorch-Abhängigkeit im sonst-
MLX-Stack. `mlx-community/bge-m3-mlx-8bit` ist inzwischen auf HF
verfügbar und geprüft.

**Lösung:** `mlx-embeddings` mit `bge-m3-mlx-8bit` — ~80 ms pro
Query-Embedding, kein PyTorch mehr im kritischen Pfad.

**Trade-off:** Minimaler Umbau beim Ingest (andere API-Signatur), sonst
gleiche Embedding-Qualität (gleiche Gewichte, 8-bit-Quant).

---

## 4. Citation Whitelist + Few-Shot statt nur Rules

**Problem:** Small instruct-LLMs (qwen3.5:0.8b, qwen3.5:2b) ignorieren
abstrakte Regeln wie "Jede Aussage mit [PARTEI – Seite X] zitieren".
Smoke-Tests zeigten 0 Citations in der Antwort. Few-Shot-Beispiele
mit konkreten Page-Nummern (`Seite 2`, `Seite 12`) führten dann zu
einem zweiten Bug: Modell **kopierte die Beispiel-Pages literally**
statt die tatsächlich retrieved Pages zu nutzen.

**Lösung:** Zwei Layer im System-Prompt:
1. **Explizite Whitelist** der zulässigen `[PARTEI – Seite X]`-Strings,
   dynamisch gebaut aus den retrieved Hits
   (`build_citation_whitelist()`).
2. Few-Shot-Beispiele bleiben für Format-Demo, aber die Whitelist
   überschreibt sie als Constraint.

**Trade-off:** ~150 zusätzliche System-Prompt-Tokens. Da `RERANK_TOP_K=3`
(siehe Punkt 5), nicht weiter problematisch.

---

## 5. `RERANK_TOP_K=3` statt 5

**Problem:** Mehr retrieved Chunks = besseres Recall, aber jeder
Chunk landet im LLM-Prompt. Bei `top_k=5` × 500 Tokens =
~2500 Token Input + ~500 Token System-Prompt → bei qwen3.5:2b-mlx
~40 s Prompt-Eval bevor das erste Antwort-Token kommt.

**Lösung:** `top_k=3` halbiert Prompt-Größe, TTFB ~14 s.

**Trade-off:** Niedrigeres Recall für Edge-Case-Fragen. Mit
`RERANK_SCORE_THRESHOLD=0.2` (statt 0.3) etwas kompensiert.

---

## 6. Thinking-Modus via `extra_body` deaktivieren

**Problem:** Qwen3 und Gemma-Modelle starten jeden Chat-Turn mit einem
internen Chain-of-Thought-Pass. Für RAG mit strikten Citation-Regeln
**bringt CoT keinen Mehrwert**, kostet aber 30–150 s TTFB. Kritischer:
beim Log-Prob-Reranker liefert `max_tokens=1` dann „Thinking" als ersten
Token statt „Ja/Nein" → Score 0.0 für alle Chunks → `below_threshold`.

**Lösung:** `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`
in allen `completions.create()`-Calls — `llm.py:chat_stream`,
`llm.py:generate`, `reranker.py:_score`. Funktioniert für alle
mlx-lm-Modelle die Qwen3/Gemma-Chat-Templates nutzen.

**Trade-off:** Bei sehr komplexen Multi-Step-Fragen wäre CoT hilfreich.
Bei "Was sagt SPD zu X" reicht direkter Lookup + Synthese.

---

## 7. Threadpool-Wrap im SSE-Endpoint

**Problem:** Alle Modell-Calls (Ollama, BGE-M3, Cross-Encoder) sind
synchron blockierend. Direkt im async-Generator
`_stream_chat` aufgerufen blockieren sie den Event-Loop — `/health`
antwortet nicht, SSE-Frames können nicht ausgespielt werden, Frontend
sieht 60-sekündige Stille.

**Lösung:** `starlette.concurrency.run_in_threadpool` um jeden
Modell-Call. Der Ollama-Token-Iterator wird per `next()` in einer
Schleife auf dem Threadpool gepumpt, ein Token nach dem anderen.

**Trade-off:** Etwas mehr Code. Aber `/health` antwortet jetzt sub-100ms
auch während einer laufenden Inferenz, und SSE-Tokens fließen
sofort.

---

## 8. CRLF-Normalisierung im Frontend-SSE-Parser

**Problem:** `sse-starlette` emittiert Felder mit `\r\n` und Event-
Blöcke mit `\r\n\r\n`. Der Frontend-Parser suchte nur nach `\n\n` →
fand nie das Event-Ende → Buffer wuchs unbegrenzt → keine Frames an
den Reducer → Frontend zeigte "keine belastbaren Stellen", obwohl
das Backend sauber gestreamt hat.

**Lösung:** `decoder.decode(...).replace(/\r\n/g, '\n')` in jedem
Chunk normalisiert CRLF zu LF bevor der `\n\n`-Scan läuft.

**Trade-off:** Minimaler Overhead pro Chunk (typisch <1 ms). Macht
den Parser robust gegen beide Line-Ending-Stile.

---

## 9. Forward-Compat Seam in `frontend/src/api/chatStream.js`

**Problem:** Während der Design-Integration (Session F) war Backend
noch nicht stabil/fertig. Komponenten brauchten Mock-Daten zum
Stylen. Ein nachträglicher Refactor "Mock → echte SSE" hätte das
Reducer-/Dispatcher-Logic-Layer ändern müssen.

**Lösung:** `chatStream({...})` ist async-Iterable, yielded
`{event, data}`-Frames. Diese Form bedienen sowohl `mockStream` als
auch der reale Fetch-Parser. Reducer dispatcht ungebunden vom Source.
`?scenario=streaming` switcht zur Laufzeit zwischen Backend und Mock.

**Trade-off:** Etwas mehr Bootstrap-Code im `chatStream.js`. Lohnt
sich — `VITE_USE_MOCKS=true` blockiert das echte Netzwerk komplett,
nützlich für Storybook-Demos und Offline-Design-Review.

---

Weitere Details zu jedem Punkt siehe Modulen direkt:

- `backend/llm.py` (enable_thinking=False, OpenAILLM)
- `backend/reranker.py` (Log-Prob Ja/Nein, extra_body)
- `backend/prompt_builder.py` (Whitelist, Few-Shot)
- `backend/main.py` (Threadpool, SSE-Event-Reihenfolge)
- `frontend/src/api/chatStream.js` (Mock-Seam, CRLF)
- `frontend/src/state/chatStore.js` (Reducer-Actions)
