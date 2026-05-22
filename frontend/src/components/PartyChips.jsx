import { PARTIES } from '../constants/parties.js'
import { useChat } from '../state/chatStore.js'

function CheckIcon() {
  return (
    <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
      <path d="M5 12l4 4 10-10" />
    </svg>
  )
}

export default function PartyChips() {
  const { state, dispatch } = useChat()
  const active = state.partyFilter

  const toggle = (slug) => {
    const next = active.includes(slug)
      ? active.filter((s) => s !== slug)
      : [...active, slug]
    dispatch({ type: 'SET_PARTY_FILTER', partyFilter: next })
  }

  const setAll = () => {
    dispatch({ type: 'SET_PARTY_FILTER', partyFilter: PARTIES.map((p) => p.slug) })
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <p className="frame-label text-bone3">Parteien</p>
        <button
          type="button"
          onClick={setAll}
          className="text-[11px] text-bone3 hover:text-bone underline underline-offset-2"
        >
          Alle
        </button>
      </div>
      <div className="mt-3 space-y-1.5 text-bone">
        {PARTIES.map((p) => {
          const on = active.includes(p.slug)
          return (
            <label
              key={p.slug}
              className={`flex items-center gap-3 text-[13px] py-1 cursor-pointer ${
                on ? '' : 'text-bone3'
              }`}
            >
              <input
                type="checkbox"
                checked={on}
                onChange={() => toggle(p.slug)}
                className="sr-only"
              />
              <span className={`check ${on ? 'on' : ''}`}>{on ? <CheckIcon /> : null}</span>
              <span>{p.label}</span>
            </label>
          )
        })}
      </div>
      <p className="mt-3 text-[11px] text-bone3 font-mono">
        {active.length} / {PARTIES.length} aktiv
      </p>
    </div>
  )
}
