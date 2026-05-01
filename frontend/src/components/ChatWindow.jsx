import { useEffect, useRef } from 'react'
import { FileText, MessageSquare, Shield } from 'lucide-react'
import MessageBubble from './MessageBubble'

function ChatWindow({ messages, onDocSelect }) {
  const bottomRef = useRef(null)
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  return (
    <main className="chat-window">
      {messages.length === 0 && (
        <div className="empty-state">
          <div className="empty-wordmark">DocLens</div>
          <p className="empty-tagline">Ask anything about your documents. Get answers cited by source.</p>

          <div className="empty-cards">
            <div className="empty-card">
              <FileText size={18} className="empty-card-icon" />
              <div className="empty-card-title">Upload any document</div>
              <div className="empty-card-desc">PDF, DOCX, or Markdown — any length. Pages are unlimited.</div>
            </div>
            <div className="empty-card">
              <MessageSquare size={18} className="empty-card-icon" />
              <div className="empty-card-title">Ask in plain language</div>
              <div className="empty-card-desc">Summaries, specific facts, comparisons — the model searches and answers.</div>
            </div>
            <div className="empty-card">
              <Shield size={18} className="empty-card-icon" />
              <div className="empty-card-title">Your key, your data</div>
              <div className="empty-card-desc">API keys stay in your browser. Documents expire after 24 hours.</div>
            </div>
          </div>

          <p className="empty-privacy">Add your API key in <strong>API Settings</strong> to get started.</p>
        </div>
      )}

      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} onDocSelect={onDocSelect} />
      ))}

      <div ref={bottomRef} />
    </main>
  )
}

export default ChatWindow
