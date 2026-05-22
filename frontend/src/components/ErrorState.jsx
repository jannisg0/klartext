import { useChat } from '../state/chatStore.js'

export default function ErrorState() {
  const { state, dispatch } = useChat()
  const reset = () => dispatch({ type: 'RESET' })

  return (
    <div className="max-w-[720px] mx-auto py-8">
      <div className="rounded-lg border border-rustDark/40 bg-graphite2/40 p-6">
        <div className="flex items-center gap-2 mb-3">
          <span className="frame-label text-rustDark">Fehler</span>
        </div>
        <p className="text-[17px] font-display text-bone leading-snug">
          Klartext konnte die Anfrage nicht beantworten.
        </p>
        <p className="mt-3 text-[14px] text-bone2 leading-relaxed">
          {state.error ?? 'Unbekannter Fehler.'}
        </p>
        <p className="mt-2 text-[12px] text-bone3">
          Prüfe, ob das Backend (uvicorn) auf <span className="font-mono">:8000</span>{' '}
          läuft und Ollama erreichbar ist.
        </p>

        <div className="mt-6">
          <button
            type="button"
            onClick={reset}
            className="h-10 px-4 rounded-md bg-bone text-graphite text-[13px] font-medium"
          >
            Erneut versuchen
          </button>
        </div>
      </div>
    </div>
  )
}
