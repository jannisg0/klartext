import { mockStream } from '../mocks/mockStream.js'

// Forward-compat seam. The async-iterable shape and the
// { event, data } frame are part of the contract the UI is
// written against. Session F2 replaces the body with a real
// SSE client (POST /chat, parse text/event-stream) without
// changing what consumers see.

const USE_MOCKS = import.meta.env.VITE_USE_MOCKS !== 'false'

export async function* chatStream({ query, partyFilter, politician, history, signal } = {}) {
  void query
  void partyFilter
  void politician
  void history
  void signal

  if (USE_MOCKS) {
    const scenario = new URLSearchParams(globalThis.location?.search ?? '').get('scenario')
    yield* mockStream(scenario || 'streaming')
    return
  }

  throw new Error('real SSE client lands in Session F2 (set VITE_USE_MOCKS=false then)')
}
