import { mockStream } from '../mocks/mockStream.js'

// Forward-compat seam. The async-iterable shape and the
// { event, data } frame are part of the contract the UI is
// written against. Same shape today (mock + real) so the
// reducer dispatcher never had to change.
//
// Dispatch rules:
//   ?scenario=NAME -> mock scenario (handy for design states)
//   otherwise      -> real POST /chat against the FastAPI backend
//   VITE_USE_MOCKS=true (env) -> always mocks (overrides URL)

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? 'http://127.0.0.1:8000'
const FORCE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true'

function readScenarioOverride() {
  if (typeof globalThis.location === 'undefined') return null
  return new URLSearchParams(globalThis.location.search).get('scenario')
}

function parseSseBlock(block) {
  let event = null
  const data = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  if (!event) return null
  const raw = data.join('\n')
  try {
    return { event, data: JSON.parse(raw) }
  } catch {
    return { event, data: raw }
  }
}

async function* parseSse(reader) {
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    while (true) {
      const sep = buffer.indexOf('\n\n')
      if (sep === -1) break
      const block = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const frame = parseSseBlock(block)
      if (frame) yield frame
    }
  }
  if (buffer.trim()) {
    const frame = parseSseBlock(buffer)
    if (frame) yield frame
  }
}

async function* realStream({ query, partyFilter, politician, history, signal }) {
  const body = JSON.stringify({
    query,
    party_filter: partyFilter && partyFilter.length ? partyFilter : null,
    politician: politician ?? null,
    history: history ?? [],
  })
  const resp = await fetch(`${BACKEND_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body,
    signal,
  })
  if (!resp.ok || !resp.body) {
    const detail = await resp.text().catch(() => '')
    throw new Error(`Backend ${resp.status} ${resp.statusText}: ${detail}`)
  }
  yield* parseSse(resp.body.getReader())
}

export async function* chatStream(opts = {}) {
  if (FORCE_MOCKS) {
    yield* mockStream(readScenarioOverride() ?? 'streaming')
    return
  }
  const override = readScenarioOverride()
  if (override) {
    yield* mockStream(override)
    return
  }
  yield* realStream(opts)
}
