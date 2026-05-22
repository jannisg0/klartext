import { useChat } from '../state/chatStore.js'

export default function BelowThresholdState() {
  const { state, dispatch } = useChat()
  const reset = () => dispatch({ type: 'RESET' })

  return (
    <div className="max-w-[720px] mx-auto py-8">
      <div className="flex items-baseline gap-3 mb-3">
        <span className="frame-label text-bone3">Antwort · Klartext</span>
        <span className="font-mono text-[11px] text-bone3">0 Quellen · 0 Belege</span>
      </div>

      <div className="rounded-lg border border-edge bg-graphite2/40 p-6">
        <p className="text-[17px] font-display text-bone leading-snug">
          Dazu finden sich keine belastbaren Stellen in den ausgewählten Wahlprogrammen.
        </p>
        <p className="mt-4 text-[14px] text-bone2 leading-relaxed">
          Mögliche Gründe: Die Frage berührt ein Thema, das in den ausgewählten
          Programmen nicht behandelt wird, oder die Begriffe weichen vom Originaltext
          ab. Ändere die Auswahl links oder formuliere die Frage konkreter um.
        </p>
        <p className="mt-3 text-[12px] text-bone3 font-mono">
          Frage war: „{state.query}"
        </p>

        <div className="mt-6 flex items-center gap-3">
          <button
            type="button"
            onClick={reset}
            className="h-10 px-4 rounded-md bg-bone text-graphite text-[13px] font-medium"
          >
            Neue Frage stellen
          </button>
        </div>
      </div>
    </div>
  )
}
