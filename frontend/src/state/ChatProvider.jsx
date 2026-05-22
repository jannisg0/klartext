import { useReducer } from 'react'
import { ChatContext, chatReducer, initialState } from './chatStore.js'

export function ChatProvider({ children }) {
  const [state, dispatch] = useReducer(chatReducer, initialState)
  return <ChatContext.Provider value={{ state, dispatch }}>{children}</ChatContext.Provider>
}
