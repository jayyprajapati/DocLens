import { useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble'

function ChatWindow({ messages, isSending }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isSending])

  return (
    <main className="chat-window">
      {messages.length === 0 && (
        <div className="empty-state">Upload a file, then ask a question about its contents.</div>
      )}

      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}

      {isSending && (
        <div className="message-row assistant">
          <div className="message-bubble assistant typing">Thinking...</div>
        </div>
      )}

      <div ref={bottomRef} />
    </main>
  )
}

export default ChatWindow