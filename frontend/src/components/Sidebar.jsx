import { PARTIES } from '../constants/parties.js'
import { useChat } from '../state/chatStore.js'
import PartyChips from './PartyChips.jsx'
import PersonaSelector from './PersonaSelector.jsx'

export default function Sidebar() {
  const { dispatch } = useChat()

  const newConversation = () => dispatch({ type: 'RESET' })

  const resetFilters = () => {
    dispatch({ type: 'SET_PARTY_FILTER', partyFilter: [] })
    dispatch({ type: 'SET_POLITICIAN', politician: null })
  }

  // Default to all parties active so the first run hits the broadest set.
  // We do this lazily here so the empty initial state still reads "0/6 aktiv"
  // before the user has interacted - and bumps to 6/6 the moment they hit
  // "Alle" in PartyChips.
  void PARTIES

  return (
    <aside className="border-r border-edge flex flex-col min-h-0">
      <div className="px-5 h-14 flex items-center hair">
        <span className="wordmark text-[22px] text-bone leading-none">Klartext</span>
      </div>

      <div className="px-5 py-5 overflow-y-auto pane flex-1">
        <button
          type="button"
          onClick={newConversation}
          className="w-full h-10 rounded-md bg-bone text-graphite text-[13px] font-medium flex items-center justify-center gap-2 hover:opacity-95"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
          Neue Unterhaltung
        </button>

        <div className="mt-8">
          <PartyChips />
        </div>

        <div className="mt-8">
          <PersonaSelector />
        </div>
      </div>

      <div className="px-5 h-12 flex items-center justify-between border-t border-edge text-[12px]">
        <button
          type="button"
          onClick={resetFilters}
          className="text-bone3 hover:text-bone flex items-center gap-1.5"
        >
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
          >
            <path d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5" />
          </svg>
          Filter zurücksetzen
        </button>
        <span className="font-mono text-bone3">⌘R</span>
      </div>
    </aside>
  )
}
