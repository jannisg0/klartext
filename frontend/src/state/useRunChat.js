import { useCallback } from 'react'
import { chatStream } from '../api/chatStream.js'
import { useChat } from './chatStore.js'

// Drives the chatStream async-iterable, dispatching each frame
// into the reducer. Same shape today (mock) and in Session F2
// (real SSE) - consumers don't change.
export function useRunChat() {
  const { state, dispatch } = useChat()

  return useCallback(
    async (query) => {
      if (!query?.trim()) return
      dispatch({ type: 'START', query })
      try {
        for await (const frame of chatStream({
          query,
          partyFilter: state.partyFilter,
          politician: state.politician,
          history: state.history,
        })) {
          const { event, data } = frame
          if (event === 'sources') dispatch({ type: 'SOURCES', sources: data })
          else if (event === 'token') dispatch({ type: 'TOKEN', text: data.text })
          else if (event === 'citations') dispatch({ type: 'CITATIONS', citations: data })
          else if (event === 'done') dispatch({ type: 'DONE' })
          else if (event === 'error')
            dispatch({ type: 'ERROR', error: data?.message ?? 'Unbekannter Fehler' })
        }
      } catch (err) {
        dispatch({ type: 'ERROR', error: err.message ?? String(err) })
      }
    },
    [state.partyFilter, state.politician, state.history, dispatch],
  )
}
