# API-Kontrakt

FastAPI-App in `backend/main.py`. Bindet auf `http://127.0.0.1:8001`
per Default. CORS-Allow-Origin per `CORS_ORIGIN` env-var
(`http://localhost:5173` Default für Vite-Dev).

---

## `GET /health`

Sofortige Health-Probe für Frontend + Watchdogs.

**Response 200:**
```json
{
  "status": "ok",
  "ollama": true,
  "chromadb": true,
  "bm25": true,
  "chunks": 62
}
```

Felder:
- `status`: `"ok"` wenn alle drei Probes passen, sonst `"degraded"`.
- `ollama` / `chromadb` / `bm25`: Bool je Probe.
- `chunks`: aktuelle Chunk-Anzahl in der Collection `klartext_manifestos`.

Antwortet **sub-100 ms** auch während einer laufenden `/chat`-Inferenz
(threadpool-Wrap im Streaming-Endpoint, siehe
[`DESIGN-DECISIONS.md`](DESIGN-DECISIONS.md#7-threadpool-wrap-im-sse-endpoint)).

---

## `POST /chat`

Streaming-Chat mit `text/event-stream`-Response (SSE).

### Request-Body — `ChatRequest`

(Pydantic-Schema in `backend/models.py`.)

```json
{
  "query": "Was sagt die SPD zur Bildungspolitik?",
  "party_filter": ["spd"],
  "politician": null,
  "history": []
}
```

| Feld | Typ | Pflicht | Beschreibung |
|------|-----|---------|--------------|
| `query` | string | ja, non-blank | Nutzerfrage |
| `party_filter` | `list[str] \| null` | nein | Party-Slugs (`spd`, `cdu`, `diegrünen`, `dielinke`, `fdp`, `afd`); `null` = alle |
| `politician` | `string \| null` | nein | Politician-Key für Persona-Modus; `null` = neutral |
| `history` | `list[ChatMessage]` | nein | Vergangene Messages, max 10 wirksam (server-side gekappt) |

`ChatMessage`: `{role: "user"|"assistant", content: string}`.

### Response — SSE-Stream

Content-Type `text/event-stream; charset=utf-8`. Pro Event:
`event: NAME\r\ndata: JSON\r\n\r\n`. (CRLF per sse-starlette;
Frontend-Parser normalisiert.)

#### Reihenfolge

```
event: sources
data: [...]

event: token
data: {"text": "..."}

(weitere token-Events …)

event: citations
data: {"verified": [...], "unverified": [...]}

event: done
data: {}
```

#### `sources` — Top-K reranked Hits

```json
[
  {
    "chunk_id": "spd_p13_c0",
    "party": "spd",
    "page": 13,
    "section_path": "3.",
    "score": 0.6495,
    "text_preview": "Wir sorgen für mehr Bildungsgerechtigkeit ..."
  }
]
```

Frontend rendert das in den Sources-Panel. Wird **vor** dem LLM-Start
gesendet — User sieht sofort welche Quellen verwendet werden.

#### `token` — LLM-Token-Stream

```json
{"text": "Bild"}
```

Ein Event pro Token (Ollama-Pacing, typisch ~27 t/s mit qwen3.5:2b-mlx).
Frontend appended an `state.tokens[]` und rendert mit blinkendem
`.caret`-Cursor.

#### `citations` — Verifikations-Ergebnis

```json
{
  "verified": [
    {"party": "spd", "page": 13, "raw": "[SPD – Seite 13]"}
  ],
  "unverified": []
}
```

Wird nach Stream-Ende gesendet. Frontend hebt unverifizierte Citations
im Antwort-Text mit gestrichelter Pille (`.cite-un`) hervor; sources im
Sources-Panel bekommen ein "nicht verifiziert"-Badge.

#### `done` — Stream-Ende

```json
{}
```

Frontend setzt `status=done`. Wenn `tokens.length === 0` → es kam keine
Antwort → BelowThresholdState UI.

#### `error` — Backend-Fehler

```json
{"message": "Backend nicht erreichbar"}
```

Frontend setzt `status=error` + zeigt ErrorState. Mock-only heute; das
echte Backend sendet nie ein `error`-Event — Fehler kommen via HTTP-
Status oder ungeplantem Stream-Abbruch.

### `below_threshold`-Fall

Wenn Reranker **alle** Hits unter `RERANK_SCORE_THRESHOLD` ablehnt:

```
event: sources       data: []
event: citations     data: {"verified": [], "unverified": []}
event: done          data: {}
```

Keine `token`-Events. Frontend zeigt "keine belastbaren Stellen".

---

## CORS-Konfiguration

`backend/main.py:_register_cors` lädt `Settings.cors_origin` und setzt:

```python
allow_origins=[settings.cors_origin]
allow_credentials=True
allow_methods=["*"]
allow_headers=["*"]
```

Default `cors_origin=http://localhost:5173`. Für deploy hinter Proxy
oder andere Frontends die env-var setzen.

---

## OpenAPI / Swagger

Nicht aktiviert. Pydantic-Schemas in `backend/models.py` sind die
einzige Source-of-Truth des Contracts. FastAPI würde `/docs` und
`/openapi.json` mit minimalem Konfig-Aufwand serven — bei Bedarf
einbauen (out of scope).
