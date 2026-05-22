const SCENARIOS = ['streaming', 'below_threshold', 'error']

function readScenario() {
  return new URLSearchParams(globalThis.location?.search ?? '').get('scenario') ?? 'streaming'
}

function setScenario(next) {
  const params = new URLSearchParams(globalThis.location.search)
  params.set('scenario', next)
  const url = `${globalThis.location.pathname}?${params.toString()}`
  globalThis.history.replaceState(null, '', url)
  globalThis.location.reload()
}

export default function DevToggle() {
  const current = readScenario()

  return (
    <div className="fixed bottom-4 right-4 z-[70] flex items-center gap-2 px-3 py-2 rounded-md bg-graphite2 border border-edge shadow-ringD text-[11px] text-bone3 font-mono">
      <span>Mock</span>
      {SCENARIOS.map((s) => (
        <button
          key={s}
          type="button"
          onClick={() => setScenario(s)}
          className={`px-2 h-6 rounded ${
            s === current ? 'bg-bone text-graphite' : 'hover:bg-graphite3'
          }`}
        >
          {s}
        </button>
      ))}
    </div>
  )
}
