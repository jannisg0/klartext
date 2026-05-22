import { Fragment } from 'react'
import { useChat } from '../state/chatStore.js'
import { partyLabel } from '../constants/parties.js'

// Splits an answer on the citation regex so [PARTY – Seite X] markers
// can be rendered as pills instead of plain text. The match also tells
// us whether the citation is verified against the retrieved chunks.
const CITE_RE = /\[(\w+)\s*[–—-]\s*Seite\s+(\d+)\]/g

function renderAnswer(text, verifiedSet) {
  const out = []
  let lastIndex = 0
  let i = 0
  for (const match of text.matchAll(CITE_RE)) {
    if (match.index > lastIndex) {
      out.push(<Fragment key={`t-${i}`}>{text.slice(lastIndex, match.index)}</Fragment>)
    }
    const party = match[1].toLowerCase()
    const page = parseInt(match[2], 10)
    const verified = verifiedSet.has(`${party}|${page}`)
    out.push(
      <span key={`c-${i}`} className={verified ? 'cite cite-ver' : 'cite cite-un'}>
        <span className="dot"></span>
        {partyLabel(party)} · S. {page}
      </span>,
    )
    lastIndex = match.index + match[0].length
    i += 1
  }
  if (lastIndex < text.length) {
    out.push(<Fragment key="t-tail">{text.slice(lastIndex)}</Fragment>)
  }
  return out
}

export function UserMessage({ text, timestamp }) {
  return (
    <div className="max-w-[720px] mx-auto">
      <div className="flex items-baseline gap-3 mb-2">
        <span className="frame-label text-bone3">Frage{timestamp ? ` · ${timestamp}` : ''}</span>
      </div>
      <div className="text-[18px] font-display text-bone leading-snug">{text}</div>
    </div>
  )
}

export function AssistantMessage() {
  const { state } = useChat()
  const verifiedSet = new Set(
    state.citations.verified.map((c) => `${c.party.toLowerCase()}|${c.page}`),
  )
  const text = state.tokens.join('')
  const streaming = state.status === 'streaming'
  const sourceCount = state.sources.length
  const citationCount =
    state.citations.verified.length + state.citations.unverified.length

  return (
    <div className="max-w-[720px] mx-auto">
      <div className="flex items-baseline gap-3 mb-3">
        <span className="frame-label text-bone3">Antwort · Klartext</span>
        <span className="font-mono text-[11px] text-bone3">
          {sourceCount} Quellen · {citationCount} Belege
        </span>
      </div>

      <article className="text-[15px] leading-[1.75] text-bone whitespace-pre-wrap">
        {renderAnswer(text, verifiedSet)}
        {streaming ? <span className="caret"></span> : null}
      </article>

      {!streaming && citationCount > 0 ? (
        <div className="mt-6 flex items-center gap-4 text-[11px] text-bone3 font-mono">
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-verDark"></span>
            verifiziert · Originaltext
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-bone3"></span>
            nicht verifiziert · prüfen
          </span>
        </div>
      ) : null}
    </div>
  )
}
