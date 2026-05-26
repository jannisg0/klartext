const SCENARIOS = ['streaming', 'below_threshold', 'error']

function readScenario() {
  return new URLSearchParams(globalThis.location?.search ?? '').get('scenario')
}

function setScenario(next) {
  const params = new URLSearchParams(globalThis.location.search)
  if (next) {
    params.set('scenario', next)
  } else {
    params.delete('scenario')
  }
  const qs = params.toString()
  const url = `${globalThis.location.pathname}${qs ? `?${qs}` : ''}`
  globalThis.history.replaceState(null, '', url)
  globalThis.location.reload()
}

export default function DevToggle() {
  const current = readScenario()
  const realActive = current === null

  return (
    <div className="fixed bottom-4 right-4 z-[70] flex items-center gap-1 px-3 py-2 rounded-md bg-graphite2 border border-edge shadow-ringD text-[11px] text-bone3 font-mono">
      <span className="mr-1">Quelle</span>
      <button
        type="button"
        onClick={() => setScenario(null)}
        className={`px-2 h-6 rounded ${
          realActive ? 'bg-bone text-graphite' : 'hover:bg-graphite3'
        }`}
        title="Echtes Backend (POST :8001/chat)"
      >
        real
      </button>
      {SCENARIOS.map((s) => (
        <button
          key={s}
          type="button"
          onClick={() => setScenario(s)}
          className={`px-2 h-6 rounded ${
            s === current ? 'bg-bone text-graphite' : 'hover:bg-graphite3'
          }`}
          title={`Mock scenario: ${s}`}
        >
          {s}
        </button>
      ))}
    </div>
  )
}
