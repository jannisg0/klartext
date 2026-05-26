import { CITATIONS_DEMO, EMPTY_CITATIONS, SOURCES_DEMO, TOKENS_DEMO } from './fixtures.js'

// Each scenario is an ordered list of { event, data } SSE-like frames.
// Mirrors the backend contract documented in backend/main.py:_stream_chat.

export const SCENARIOS = {
  empty: [],

  streaming: [
    { event: 'sources', data: SOURCES_DEMO },
    ...TOKENS_DEMO.map((text) => ({ event: 'token', data: { text } })),
    { event: 'citations', data: CITATIONS_DEMO },
    { event: 'done', data: {} },
  ],

  below_threshold: [
    { event: 'sources', data: [] },
    { event: 'citations', data: EMPTY_CITATIONS },
    { event: 'done', data: {} },
  ],

  error: [
    {
      event: 'error',
      data: { message: 'Backend nicht erreichbar (mock). Prüfe ob uvicorn auf :8001 läuft.' },
    },
  ],
}

export const SCENARIO_NAMES = Object.keys(SCENARIOS)
