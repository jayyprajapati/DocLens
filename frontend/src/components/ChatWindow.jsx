import { useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { FileText, MessageCircle, Paperclip } from 'lucide-react'
import MessageBubble from './MessageBubble'

function ChatWindow({ messages, isSending }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isSending])

  return (
    <main className="chat-window">
      {messages.length === 0 && (
        <div className="empty-state">
          <h2 className="empty-tagline">Ask your docs anything, get grounded answers.</h2>
          <p className="empty-subtitle">Attach one file and start a focused conversation.</p>

          <div className="empty-guide" role="list" aria-label="How to get started">
            <div className="empty-guide-item" role="listitem">
              <Paperclip size={15} aria-hidden="true" />
              <span>Attach one document from the input bar.</span>
            </div>
            <div className="empty-guide-item" role="listitem">
              <FileText size={15} aria-hidden="true" />
              <span>Wait for processing confirmation.</span>
            </div>
            <div className="empty-guide-item" role="listitem">
              <MessageCircle size={15} aria-hidden="true" />
              <span>Ask specific questions to get better responses.</span>
            </div>
          </div>

          <div className="empty-constraints" aria-label="Usage limits">
            Max 2 queries, 1 document, up to 3 pages.
          </div>
        </div>
      )}

      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}

      {isSending && (
        <div className="system-message system-ack system-thinking" aria-live="polite">
          <span>Thinking through your document context</span>
          <motion.span
            className="thinking-dots"
            animate={{ opacity: [0.25, 1, 0.25] }}
            transition={{ duration: 1.1, repeat: Infinity, ease: 'easeInOut' }}
          >
            ...
          </motion.span>
        </div>
      )}

      <div ref={bottomRef} />
    </main>
  )
}

export default ChatWindow