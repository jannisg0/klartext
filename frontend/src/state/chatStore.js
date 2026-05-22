import { createContext, useContext } from 'react'

// status:
//   'idle'         - no run in flight, EmptyState if history is empty
//   'streaming'    - request running; sources may have arrived, tokens flowing
//   'done'         - run finished; below-threshold = done && tokens.length === 0
//   'error'        - request failed (network, backend, LLM)
export const initialState = {
  status: 'idle',
  query: '',
  sources: [],
  tokens: [],
  citations: { verified: [], unverified: [] },
  error: null,
  partyFilter: [],
  politician: null,
  history: [],
}

export function chatReducer(state, action) {
  switch (action.type) {
    case 'RESET':
      return { ...initialState, partyFilter: state.partyFilter, politician: state.politician }
    case 'START':
      return {
        ...state,
        status: 'streaming',
        query: action.query,
        sources: [],
        tokens: [],
        citations: { verified: [], unverified: [] },
        error: null,
      }
    case 'SOURCES':
      return { ...state, sources: action.sources }
    case 'TOKEN':
      return { ...state, tokens: [...state.tokens, action.text] }
    case 'CITATIONS':
      return { ...state, citations: action.citations }
    case 'DONE':
      return { ...state, status: 'done' }
    case 'ERROR':
      return { ...state, status: 'error', error: action.error }
    case 'SET_PARTY_FILTER':
      return { ...state, partyFilter: action.partyFilter }
    case 'SET_POLITICIAN':
      return { ...state, politician: action.politician }
    default:
      return state
  }
}

export const ChatContext = createContext(null)

export function useChat() {
  const ctx = useContext(ChatContext)
  if (!ctx) throw new Error('useChat must be used inside <ChatProvider>')
  return ctx
}
