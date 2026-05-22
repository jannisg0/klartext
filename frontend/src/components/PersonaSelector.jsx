import { useChat } from '../state/chatStore.js'

// Persona options come from data/tweets/*.json at the backend level;
// for the design-only session these are hard-coded placeholders so the
// radio UI has something to render.
const OPTIONS = [
  { value: null, label: 'Neutraler Modus' },
  { value: 'annalena_baerbock', label: 'Annalena Baerbock · Grüne' },
  { value: 'friedrich_merz', label: 'Friedrich Merz · CDU' },
]

export default function PersonaSelector() {
  const { state, dispatch } = useChat()

  const choose = (value) => dispatch({ type: 'SET_POLITICIAN', politician: value })

  return (
    <div>
      <p className="frame-label text-bone3">Persona</p>
      <div className="mt-3 space-y-1.5">
        {OPTIONS.map((opt) => {
          const on = state.politician === opt.value
          return (
            <label
              key={opt.value ?? 'neutral'}
              className={`flex items-center gap-3 text-[13px] py-1 cursor-pointer ${
                on ? 'text-bone' : 'text-bone3'
              }`}
            >
              <input
                type="radio"
                name="persona"
                checked={on}
                onChange={() => choose(opt.value)}
                className="sr-only"
              />
              <span className={`radio ${on ? 'on' : ''}`}></span>
              <span>{opt.label}</span>
            </label>
          )
        })}
      </div>
    </div>
  )
}
