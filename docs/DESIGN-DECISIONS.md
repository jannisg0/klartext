# Design-Entscheidungen

Die Stationen, an denen wir die Architektur gegen einen schmerzhaften
Trade-off entschieden haben. Jeder Eintrag: Problem, Lösung, was wir
aufgegeben haben.

---

## 1. MLX via Ollama-MLX-Runner statt direkt `mlx-lm`

**Problem:** Ursprünglich war `mlx_lm.load(...)` der direkte Pfad.
Funktioniert für klassische LLMs, aber das vom Nutzer gewünschte
`gemma4:e4b` ist multimodal — die Gewichte liegen unter
`language_model.model.layers.*` statt `model.layers.*`. `mlx-lm`
crasht beim Laden mit `ValueError: Received 126 parameters not in
model`.

**Lösung:** Ollama hat seit v0.19 einen nativen MLX-Runner. Tags
wie `gemma4:e4b-mlx`, `qwen3.5:2b-mlx` werden auf Apple Silicon
direkt via MLX ausgeführt, ohne dass wir den Loader im Code anfassen.
Wir setzen `LLM_BACKEND=ollama` mit MLX-Tags als Modellnamen.

**Trade-off:** Ollama-Layer ist ein extra Prozess + HTTP-Overhead
zwischen unserem Backend und dem Modell. Auf Apple Silicon
vernachlässigbar (~50 ms pro Request). `MlxLLM`-Klasse bleibt im
Code für direkte mlx-lm-Nutzung wenn jemand das später wieder
braucht.

---

## 2. qwen3.5:2b-mlx als Default-LLM

**Problem:** `qwen3:14b` (~9 GB) auf 16 GB Mac liefert hochwertige
Antworten, braucht aber 170–300 s Wall-Time für eine Frage —
unbenutzbar. `gemma4:e4b-mlx` (~9.6 GB, MoE) ist
qualitativ ähnlich aber selbst mit `think=False` ~30 s TTFB wegen
großer Prompt-Eval.

**Lösung:** `qwen3.5:2b-mlx` (3.1 GB) bei ~24 s Wall-Time, ~14 s
TTFB. Citation-Discipline kommt nicht von alleine — kleinere Modelle
ignorieren das `[PARTEI – Seite X]`-Format. Daher Few-Shot-Beispiele
im System-Prompt + explizite Whitelist der erlaubten Citations
(siehe Punkt 4).

**Trade-off:** Antworten knapper als bei 14B-Modellen. Quality-vs-
Speed-Sweet-Spot für interaktiven Chat. `LLM_BACKEND=ollama` +
`OLLAMA_MODEL_MAIN=qwen3:14b` bleibt als A/B-Escape-Hatch.

---

## 3. BGE-M3 bleibt PyTorch / MPS, nicht MLX

**Problem:** Konsistenz im Stack — "alles auf MLX" — würde auch das
Embedding-Modell verlangen. `mlx-embeddings` existiert, aber
`mlx-community/bge-m3-mlx` ist nicht offiziell publiziert; auf HF
auffindbare Konvertierungen sind selten und nicht durchgehend
geprüft.

**Lösung:** `BAAI/bge-m3` läuft via `FlagEmbedding` auf MPS — auf
Apple Silicon ~80 ms pro Query-Embedding. Kein Bottleneck.

**Trade-off:** Eine PyTorch-Abhängigkeit für sonst-MLX-Stack. Akzeptabel,
weil Embedding nur einmal pro Query (statt 700× pro Token-Stream)
läuft.

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

## 6. `think=False` auf Ollama-Calls

**Problem:** Gemma 4 und Qwen3-Familie expose ein "thinking"-Feature
— internes Chain-of-Thought-Pass vor der eigentlichen Antwort. Für
RAG mit strikten Citation-Regeln **bringt CoT keinen Mehrwert**, kostet
aber 30–150 s zusätzliche TTFB.

**Lösung:** `ollama.chat(..., think=False)` in
`backend/llm.py:OllamaLLM.chat_stream`. Modelle ohne thinking-Feature
ignorieren das Flag.

**Trade-off:** Bei sehr komplexen Multi-Step-Fragen wäre CoT
hilfreich. Bei "Was sagt SPD zu X" reicht direkter Lookup +
Synthese — kein CoT nötig.

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

- `backend/llm.py` (think=False, MlxLLM, OllamaLLM)
- `backend/prompt_builder.py` (Whitelist, Few-Shot)
- `backend/main.py` (Threadpool, SSE-Event-Reihenfolge)
- `frontend/src/api/chatStream.js` (Mock-Seam, CRLF)
- `frontend/src/state/chatStore.js` (Reducer-Actions)
