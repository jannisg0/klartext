import { useChat } from '../state/chatStore.js'
import { partyLabel } from '../constants/parties.js'

function SourceItem({ hit, verified }) {
  const score = Math.round((hit.score ?? 0) * 100)
  const fill = `${Math.min(100, Math.max(2, score))}%`
  return (
    <article className="px-5 py-4 border-b border-edge hover:bg-graphite2/60 cursor-pointer">
      <div className="flex items-start justify-between gap-3">
        <div className="leading-tight">
          <div className="text-[13px] text-bone font-medium">{partyLabel(hit.party)}</div>
          <div className="text-[11px] text-bone3 font-mono">{hit.section_path}</div>
        </div>
        <div className="text-right">
          <div className="font-mono text-[11px] text-bone3">S. {hit.page}</div>
          <div
            className={`font-mono text-[11px] mt-0.5 ${verified ? 'text-verDark' : 'text-bone3'}`}
          >
            {(hit.score ?? 0).toFixed(2)}
          </div>
        </div>
      </div>
      <div className="score-bar mt-2">
        <div className={`score-fill ${verified ? 'ver' : ''}`} style={{ width: fill }}></div>
      </div>
      <p className="mt-3 text-[12.5px] text-bone2 leading-relaxed">{hit.text_preview}</p>
      {!verified ? (
        <div className="mt-3 flex items-center gap-3 text-[11px] text-bone3 font-mono">
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-bone3"></span>
            nicht verifiziert
          </span>
        </div>
      ) : null}
    </article>
  )
}

export default function SourcesPanel() {
  const { state } = useChat()
  const verifiedSet = new Set(
    state.citations.verified.map((c) => `${c.party.toLowerCase()}|${c.page}`),
  )

  return (
    <aside className="border-l border-edge flex flex-col min-h-0">
      <div className="h-14 px-5 flex items-center justify-between hair">
        <div className="flex items-center gap-2">
          <span className="frame-label text-bone3">Quellen</span>
          <span className="font-mono text-[11px] text-bone3">
            {state.sources.length} / {state.sources.length || 0}
          </span>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto pane">
        {state.sources.length === 0 ? (
          <div className="p-5 text-[12.5px] text-bone3 italic">
            Noch keine Quellen. Stelle eine Frage links.
          </div>
        ) : (
          state.sources.map((hit) => (
            <SourceItem
              key={hit.chunk_id}
              hit={hit}
              verified={verifiedSet.has(`${hit.party.toLowerCase()}|${hit.page}`)}
            />
          ))
        )}
      </div>

      <div className="h-12 px-5 flex items-center justify-between border-t border-edge text-[11px] text-bone3">
        <span className="font-mono">Hybrid-Retrieval · Cross-Encoder</span>
      </div>
    </aside>
  )
}
