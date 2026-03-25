import { useEffect, useRef } from 'react'
import { KeyRound, MessageCircle, Paperclip, Sparkles } from 'lucide-react'
import MessageBubble from './MessageBubble'

function ChatWindow({ messages, loadingState, loadingTask }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, loadingState])

  const processingLabel =
    loadingState === 'generating'
      ? 'Generating answer...'
      : loadingState === 'retrieving' && loadingTask === 'upload'
        ? 'Uploading and indexing your document...'
        : loadingState === 'retrieving'
          ? 'Searching your document...'
          : null

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

          <div className="empty-restriction-row" role="list" aria-label="Free tier limits">
            <span role="listitem">Max 1 document</span>
            <span role="listitem">Max 3 pages</span>
            <span role="listitem">Max 2 free questions</span>
          </div>

          <div className="empty-constraints" aria-label="BYOK note">
            <KeyRound size={14} aria-hidden="true" />
            <span>BYOK model access expands usage with fewer practical limits.</span>
          </div>
        </div>
      )}

      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}

      {processingLabel && (
        <div className="processing-indicator" role="status" aria-live="polite">
          <span className="processing-spinner" aria-hidden="true" />
          <span>{processingLabel}</span>
        </div>
      )}

      <div ref={bottomRef} />
    </main>
  )
}

export default ChatWindow