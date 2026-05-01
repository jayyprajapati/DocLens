import { useEffect, useRef } from 'react'
import { MessageCircle, Paperclip, Sparkles } from 'lucide-react'
import MessageBubble from './MessageBubble'

function ChatWindow({ messages }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  return (
    <main className="chat-window">
      {messages.length === 0 && (
        <div className="empty-state">
          <h2 className="empty-tagline">DocLens: focused AI chat for documents</h2>
          <p className="empty-subtitle">Upload once, ask clearly, and get grounded answers.</p>

          <div className="empty-feature-row" role="list" aria-label="Core features">
            <div className="empty-feature-item" role="listitem">
              <Paperclip size={16} aria-hidden="true" />
              <span>Document Upload</span>
            </div>
            <div className="empty-feature-item" role="listitem">
              <MessageCircle size={16} aria-hidden="true" />
              <span>Context Chat</span>
            </div>
            <div className="empty-feature-item" role="listitem">
              <Sparkles size={16} aria-hidden="true" />
              <span>Source-Aware Answers</span>
            </div>
          </div>

          <div className="empty-constraints" aria-label="API key required">
            <span>Add your OpenAI API key and select a model to get started.</span>
          </div>
        </div>
      )}

      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}

      <div ref={bottomRef} />
    </main>
  )
}

export default ChatWindow
