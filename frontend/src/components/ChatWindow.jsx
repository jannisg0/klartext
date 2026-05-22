import { useChat } from '../state/chatStore.js'
import { AssistantMessage, UserMessage } from './MessageBubble.jsx'
import EmptyState from './EmptyState.jsx'
import BelowThresholdState from './BelowThresholdState.jsx'
import ErrorState from './ErrorState.jsx'
import QueryInput from './QueryInput.jsx'
import SourcesPanel from './SourcesPanel.jsx'

function Topbar() {
  const { state } = useChat()
  const mode = state.politician ? `Persona · ${state.politician}` : 'Neutraler Modus'
  return (
    <div className="h-14 px-6 flex items-center justify-between hair">
      <div className="flex items-center gap-3 text-[13px] text-bone2">
        <span className="frame-label text-bone3">Auswahl</span>
        <span className="text-bone3 mx-2">·</span>
        <span className="text-bone3">{mode}</span>
      </div>
      <div className="flex items-center gap-2 text-[12px] text-bone3">
        <button type="button" className="px-2 h-7 rounded hover:bg-graphite2">
          Teilen
        </button>
        <button type="button" className="px-2 h-7 rounded hover:bg-graphite2">
          Export
        </button>
      </div>
    </div>
  )
}

function ChatScroll() {
  const { state } = useChat()

  if (state.status === 'idle' && state.tokens.length === 0) {
    return null // EmptyState is rendered at shell level instead
  }

  return (
    <div className="flex-1 min-h-0 overflow-y-auto pane px-8 py-8 space-y-8">
      {state.query ? <UserMessage text={state.query} /> : null}
      {state.status === 'error' ? (
        <ErrorState />
      ) : state.status === 'done' && state.tokens.length === 0 ? (
        <BelowThresholdState />
      ) : (
        <AssistantMessage />
      )}
    </div>
  )
}

export default function ChatWindow() {
  const { state } = useChat()
  const isEmpty = state.status === 'idle' && state.tokens.length === 0 && !state.query

  return (
    <>
      <main className="relative flex flex-col min-h-0">
        <Topbar />
        {isEmpty ? (
          <EmptyState />
        ) : (
          <>
            <ChatScroll />
            <QueryInput />
          </>
        )}
      </main>

      <SourcesPanel />
    </>
  )
}
