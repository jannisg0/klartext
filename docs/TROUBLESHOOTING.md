# Troubleshooting

Bekannte Probleme aus der Entwicklung + ihre Lösungen. Wenn dir
etwas hier nicht hilft: `tail -f logs/klartext.log` und den
Backend-Stacktrace anschauen (`uv run uvicorn ... --log-level
debug`).

---

## Backend hängt minutenlang vor dem ersten Token

**Symptom:** Curl bleibt 60–180 s ohne Bytes hängen, dann kommen
Tokens.

**Ursache:** Thinking-fähige Modelle (Gemma 4, Qwen3-Familie)
führen vor dem ersten User-Token einen internen Chain-of-Thought-
Pass aus. Bei einem 8B-Modell mit 1000-Token-Prompt kostet das
60–150 s.

**Fix:** Im Code bereits gesetzt — `extra_body={"chat_template_kwargs":
{"enable_thinking": False}}` in allen `completions.create()`-Calls in
`backend/llm.py` und `backend/reranker.py`. Sicherstellen, dass die
Dateien aktuell sind (`git log -- backend/llm.py | head` sollte
`fix(llm): disable thinking mode via extra_body for all completions calls`
enthalten).

Wer trotzdem CoT will: `enable_thinking: True` setzen und Latenz
auf ~3 min hochfahren.

---

## Frontend zeigt "keine belastbaren Stellen", obwohl curl Tokens liefert

**Symptom:** `curl POST /chat` produziert 300+ `event: token` Frames,
aber das React-Frontend zeigt sofort `BelowThresholdState`.

**Ursache:** `sse-starlette` emittiert SSE-Frames mit `\r\n` Line-
Endings und `\r\n\r\n` Event-Trenner. Ein naiver Parser, der nur
`\n\n` sucht, findet niemals das Event-Ende. Buffer wächst, keine
Frames werden an den Reducer dispatcht, `status` flippt direkt auf
`done` mit `tokens.length === 0`.

**Fix:** Im Code bereits gefixt — siehe
`frontend/src/api/chatStream.js`:

```js
buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
```

Wenn nach `git pull` noch nicht da: Vite Hot-Reload, dann
`Cmd+Shift+R` im Browser.

---

## LLM ignoriert Citation-Format / keine Pillen in der Antwort

**Symptom:** `citations`-Event kommt mit `verified: []` und
`unverified: []`. Antwort hat keine `[PARTEI – Seite X]`-Stellen.

**Ursache:** Kleine instruct-Modelle (qwen3.5:0.8b, qwen3.5:2b
ohne Few-Shot) ignorieren abstrakte Format-Regeln.

**Fix:** Im Code bereits gefixt — `backend/prompt_builder.py`
enthält Few-Shot-Beispiele + dynamische Citation-Whitelist
(`build_citation_whitelist(hits)`). Wenn nach `git pull`
die Citations immer noch fehlen: Backend neu starten, dass die
neue System-Prompt-Version geladen wird.

---

## "Modell zitiert nur Seiten 2/3/12" obwohl Sources andere Seiten zeigen

**Symptom:** Sources im Frontend zeigen z. B. Seiten 5, 7, 21.
Antwort zitiert aber `[SPD – Seite 2]` und `[SPD – Seite 12]`, die
nicht in den Sources sind → alle als `unverified` markiert.

**Ursache:** Kleine LLMs **kopieren** Page-Nummern aus den Few-
Shot-Beispielen literally — besonders wenn die Frage thematisch
ähnlich zum Beispiel ist.

**Fix:** Dynamisch generierte Whitelist im System-Prompt
(`build_citation_whitelist`) listet exakt die zulässigen Citations
für genau diese Anfrage. Bereits eingebaut. Wenn das Symptom auf
deinem System auftritt: Code-Stand prüfen
(`git log backend/prompt_builder.py | head`).

---

## `ValueError: Received 126 parameters not in model`

**Symptom:** `mlx_lm.server` crasht beim Start.

**Ursache:** Multimodales Modell (VLM) — Gewichte unter
`language_model.model.*` statt `model.layers.*`. `mlx-lm` versteht
das Layout nicht.

**Fix:** Anderes Modell wählen. Empfohlen: `mlx-community/Qwen3.5-2B-OptiQ-4bit`
(reines LLM, kein VLM). Oder `LLM_BACKEND=ollama` + Ollama-MLX-Runner
der VLMs unterstützt.

---


## "Port 5173 / 8000 / 8001 is already in use"

**Symptom:** Vite, mlx-lm Server oder Uvicorn schmeißt bei Start einen Bind-Error.

**Ursache:** Ein Zombie-Prozess hält noch den Port (oft eine alte
Background-Session).

**Fix:**
```bash
lsof -nP -iTCP:5173 -sTCP:LISTEN     # Vite Frontend
lsof -nP -iTCP:8000 -sTCP:LISTEN     # mlx-lm Inference-Server
lsof -nP -iTCP:8001 -sTCP:LISTEN     # FastAPI Backend
kill <PID>
```

---

## `gemma4:e4b-mlx` braucht ewig zu downloaden / abgebrochen

**Symptom:** `ollama pull gemma4:e4b-mlx` hängt bei 33 % bei 9.6 GB.

**Ursache:** Ohne HF-Token rate-limited HF-Hub; das MoE-Modell ist
groß (9.6 GB) und die Verbindung kann mid-stream geschlossen werden.

**Fix:** Pull wiederholen — Ollama resumiert vom partial-blob. Oder
einen HF-Token in der Umgebung setzen (`HF_TOKEN=...`).

---

## "Dazu finden sich keine belastbaren Stellen" bei jeder Frage

**Symptom:** Egal welche Frage, Frontend antwortet immer mit
`BelowThresholdState`.

**Ursachen-Checklist:**
1. **Ingest gelaufen?** `curl /health | jq .chunks` — wenn 0, dann
   `uv run python -m scripts.ingest` ausführen.
2. **mlx-lm-Server läuft?** Log-Prob-Reranker schlägt lautlos fehl
   wenn `:8000` down ist → alle Scores 0.0 → `below_threshold`.
   `curl http://localhost:8000/v1/models` prüfen.
3. **Thinking-Modus aktiv?** `extra_body` fehlt oder wird vom Server
   ignoriert → „Thinking"-Token statt „Ja/Nein" → Score 0.0.
   Backend-Log zeigt `chat.empty_context below_threshold=True`.
4. **Threshold zu strikt?** `RERANK_SCORE_THRESHOLD` in `.env` auf
   `0.2` setzen.
5. **Party-Filter zu eng?** Wenn nur SPD ingestet ist und User filtert
   auf CDU → no hits. Auf "alle" stellen oder weitere PDFs ingesten.
6. **SSE-Parser-Bug** (siehe oben) — wenn curl Tokens zeigt aber
   Frontend nicht, ist es CRLF.

---

## Tests grün, Frontend-Build grün, aber `/chat` antwortet 500

**Symptom:** Uvicorn-Log zeigt `Internal Server Error`,
`backend.main` Stacktrace.

**Fix:** `uv run uvicorn ... --log-level debug` für vollständigen
Trace. Häufige Auslöser:
- ChromaDB-Collection leer (siehe oben Ingest).
- mlx-lm-Server nicht erreichbar (`uv run mlx_lm.server ...` läuft auf `:8000`?).
- BGE-M3-Modell konnte nicht geladen werden (Disk voll / HF-Cache korrupt).
