# Frontend

Vite + React + Tailwind, **kein TypeScript**. Lebt unter `frontend/`.

---

## Komponenten-Layout

```
frontend/src/
  main.jsx                     Vite-Entry, mountet App in ChatProvider
  App.jsx                      3-Spalten-Shell (Sidebar | Chat | Sources)
  index.css                    Tailwind-Layers + editorial Theme
                               (paper/ink/graphite/bone Palette, Newsreader-
                               Display-Font, .cite / .score-bar Utilities)

  constants/
    parties.js                 6 Party-Slugs + Brand-Colors + Tailwind-Keys

  state/
    chatStore.js               useReducer + Context, status ∈ {idle,streaming,
                               done,error}, Actions SOURCES/TOKEN/CITATIONS/
                               DONE/ERROR/SET_PARTY_FILTER/SET_POLITICIAN
    ChatProvider.jsx           Provider-Component
    useRunChat.js              Hook, der chatStream konsumiert + dispatcht

  api/
    chatStream.js              SSE-Client + Mock-Seam (siehe unten)

  mocks/
    fixtures.js                SourceItem/CitationsPayload/TOKENS_DEMO
    scenarios.js               streaming / below_threshold / error
    mockStream.js              async-Generator mit setTimeout-Pacing

  components/
    Sidebar.jsx                Wordmark + Neue-Unterhaltung + PartyChips +
                               PersonaSelector
    PartyChips.jsx             6 Toggle-Checkboxen aus PARTIES
    PersonaSelector.jsx        Radio-Liste (Neutral + Politiker)
    ChatWindow.jsx             Branched auf state.status → Empty/Streaming/
                               BelowThreshold/Error
    EmptyState.jsx             Wordmark-Headline + Suchfeld + 4 Beispiele
    MessageBubble.jsx          UserMessage + AssistantMessage mit Inline-
                               Citation-Pills (.cite-ver / .cite-un)
    SourcesPanel.jsx           Top-K Hits mit Score-Bar
    BelowThresholdState.jsx    "keine belastbaren Stellen" Panel
    ErrorState.jsx             Backend-Down Panel
    QueryInput.jsx             Textarea + Submit, Enter sendet
    DevToggle.jsx              Bottom-right: real | streaming | below_threshold
                               | error → flippt ?scenario=
```

---

## Dev-Loop

```bash
cd frontend
npm install            # einmalig
npm run dev            # bindet 127.0.0.1:5173 strict
```

Vite-HMR reloaded automatisch beim Save. Bei Tailwind-Klassen-Änderungen
im `tailwind.config.js` muss man manchmal hart reloaden (`Cmd+Shift+R`).

Build + Lint:
```bash
npm run build           # erzeugt dist/, ~67 kB JS gzipped
npm run lint            # ESLint flat-config + react-hooks
npm run format          # Prettier
```

---

## Source-of-Truth: `chatStream`

`frontend/src/api/chatStream.js` ist die einzige Stelle, die das Backend
aufruft. Async-Generator-Signatur:

```js
async function* chatStream({ query, partyFilter, politician, history, signal })
```

Yielded `{event, data}`-Frames in derselben Form wie das Backend sie
sendet (siehe [`API.md`](API.md)).

### Branching:

1. `?scenario=streaming|below_threshold|error` in der URL → mock-only
   (ignoriert Backend).
2. `VITE_USE_MOCKS=true` per env → erzwungener Mock (für Storybook /
   offline-Demos).
3. Sonst: `fetch('http://127.0.0.1:8000/chat', {body, signal})` mit
   Streaming-Response, manuelle SSE-Parsing.

### CRLF-Normalisierung (kritisch)

`sse-starlette` emittiert mit `\r\n` Line-Endings. Der Parser
normalisiert pro Chunk:

```js
buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
```

Sonst findet `buffer.indexOf('\n\n')` nie das Event-Ende → Reducer
sieht keine Frames → ChatWindow zeigt fälschlich BelowThresholdState.
Siehe [`DESIGN-DECISIONS.md`](DESIGN-DECISIONS.md#8-crlf-normalisierung-im-frontend-sse-parser).

---

## DevToggle + Mock-Szenarien

Bottom-right schwebende Leiste mit 4 Knöpfen. Klick rewritet die URL
(`?scenario=NAME`) und reloaded.

| Szenario | Verhalten |
|----------|-----------|
| `real` (kein Param) | Echtes Backend, normale SSE-Tokens |
| `streaming` | Mock: 5 Sources + ~20 Tokens + Citations + done |
| `below_threshold` | Mock: leere Sources + leere Citations + done |
| `error` | Mock: einzelnes `error`-Frame, ErrorState rendert |

Nützlich für UI-Design ohne Backend, für Screenshots aller States,
und zur Reproduktion von Edge-Cases im UI-Code.

---

## State-Management

Bewusst minimal: ein `useReducer` in `state/chatStore.js`. Kein Redux,
Zustand, RTK. Reducer-Actions sind in PIPELINE.md beschrieben.

`status`-Werte:
- `idle` — Initial, keine Anfrage in Flight. Wenn `tokens.length === 0`
  → EmptyState; sonst keep last answer.
- `streaming` — Anfrage läuft, sources/tokens kommen.
- `done` — Stream geschlossen.
  - `tokens.length > 0` → AssistantMessage anzeigen.
  - `tokens.length === 0` → BelowThresholdState.
- `error` — Backend-Fehler oder Network-Drop → ErrorState.

---

## Tailwind-Theme

Editorial Stil aus `docs/design/Klartext.html` (Claude-Design Handover):
- **Paper** (Light Mode): `#F4F1EA`, `#EBE7DB`, …
- **Graphite** (Dark Mode, Default): `#131210`, `#1B1A16`, …
- **Akzente**: `ochre` (Warnungen), `rust` (Errors), `ver` (verified
  Citations, gedämpftes Moosgrün).
- **Fonts**: `Newsreader` (Display-Headlines), `Geist` (Body),
  `JetBrains Mono` (Mono / Citation-Pills).
- **Custom Utilities** in `index.css`: `.cite`, `.cite-ver`, `.cite-un`,
  `.score-bar`, `.score-fill`, `.caret` (blinkender Streaming-Cursor),
  `.grain` (Papier-Noise-Overlay), `.hair` (Trennlinien).

Komplette Token-Tabelle in `tailwind.config.js`.
