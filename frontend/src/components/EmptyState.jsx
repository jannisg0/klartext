import { useState } from 'react'
import { useRunChat } from '../state/useRunChat.js'

const EXAMPLES = [
  'Wie unterscheiden sich die Parteien beim Mindestlohn?',
  'Welche Pläne gibt es für den Wohnungsmarkt?',
  'Wer fordert eine Reform der Schuldenbremse?',
  'Wie positionieren sich die Parteien zur Wehrpflicht?',
]

export default function EmptyState() {
  const runChat = useRunChat()
  const [value, setValue] = useState('')

  const submit = (q) => {
    const query = (q ?? value).trim()
    if (!query) return
    setValue('')
    runChat(query)
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col items-center justify-center px-6 reveal">
      <p className="frame-label text-bone3 mb-6 tracking-[0.3em]">— K L A R T E X T —</p>

      <h1 className="wordmark text-[80px] md:text-[112px] leading-[0.95] press text-center">
        Was möchtest
        <br />
        du wissen<span className="text-ochreDark">?</span>
      </h1>

      <p className="mt-6 max-w-[520px] text-center text-[15px] leading-[1.6] text-bone2">
        Klartext beantwortet politische Fragen ausschließlich aus den Wahlprogrammen
        der im Bundestag vertretenen Parteien. Jede Aussage trägt ihre Quelle bei
        sich.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
        className="mt-10 w-full max-w-[680px] flex items-center bg-graphite2 border border-edge rounded-lg shadow-ringD focus-within:border-ochreDark"
      >
        <span className="pl-5 pr-3 text-bone3">
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="M4 7h12M4 12h16M4 17h8" />
          </svg>
        </span>
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Stelle eine Frage zu Steuern, Klima, Bildung, Rente …"
          className="flex-1 h-14 bg-transparent text-[15px] text-bone placeholder:text-bone3 ring-soft"
        />
        <button
          type="submit"
          className="mr-2 my-2 h-10 px-4 rounded-md bg-bone text-graphite font-medium text-[13px] flex items-center gap-2 hover:opacity-95"
        >
          Fragen
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
      </form>

      <div className="mt-7 w-full max-w-[680px]">
        <p className="frame-label text-bone3 mb-3">Beispielfragen</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {EXAMPLES.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => submit(q)}
              className="text-left px-4 py-3 rounded-md border border-edge hover:bg-graphite2 transition text-[13px] text-bone2"
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
