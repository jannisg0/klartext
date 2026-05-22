import { useState } from 'react'
import { useChat } from '../state/chatStore.js'
import { useRunChat } from '../state/useRunChat.js'

export default function QueryInput() {
  const { state } = useChat()
  const runChat = useRunChat()
  const [value, setValue] = useState('')

  const submit = () => {
    const q = value.trim()
    if (!q || state.status === 'streaming') return
    setValue('')
    runChat(q)
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="px-8 pb-6">
      <div className="flex items-end gap-2 bg-graphite2 border border-edge rounded-lg shadow-ringD focus-within:border-ochreDark p-2">
        <textarea
          rows={2}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Frage stellen oder vertiefen …"
          className="flex-1 bg-transparent text-[14px] text-bone placeholder:text-bone3 resize-none px-3 py-2 ring-soft outline-none leading-relaxed"
        />
        <button
          type="button"
          className="h-10 px-3 rounded-md text-bone3 hover:bg-graphite3 text-[12px] font-mono"
          aria-label="Senden"
          onClick={submit}
        >
          ⏎
        </button>
        <button
          type="button"
          onClick={submit}
          disabled={state.status === 'streaming' || !value.trim()}
          className="h-10 px-4 rounded-md bg-bone text-graphite text-[13px] font-medium flex items-center gap-2 disabled:opacity-50"
        >
          Senden
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
          >
            <path d="M5 12h14M13 6l6 6-6 6" />
          </svg>
        </button>
      </div>
      <p className="mt-2 text-[11px] text-bone3 px-1">
        Enter sendet · Shift+Enter neue Zeile · Klartext kann irren – prüfe die Quellen.
      </p>
    </div>
  )
}
