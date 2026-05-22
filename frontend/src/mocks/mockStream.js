import { SCENARIOS } from './scenarios.js'

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function delayFor(event) {
  // SSE pacing in production is dominated by qwen3:14b token cadence.
  // Mock the same feel: source/citations land "instantly", tokens drip.
  if (event === 'token') return 70 + Math.random() * 60
  return 120
}

export async function* mockStream(name) {
  const frames = SCENARIOS[name] ?? SCENARIOS.streaming
  for (const frame of frames) {
    await sleep(delayFor(frame.event))
    yield frame
  }
}
