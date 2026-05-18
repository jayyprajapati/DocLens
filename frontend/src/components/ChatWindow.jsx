import { useEffect, useRef } from 'react'
import { FileKey2, FileText, MessageSquareText, ShieldCheck } from 'lucide-react'
import MessageBubble from './MessageBubble'

function ChatWindow({ messages, onDocSelect, documents = [] }) {
  const bottomRef = useRef(null)
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  const hasDocuments = documents.length > 0

  return (
    <main className="chat-window">
      {messages.length === 0 && (
        <div className="empty-state">
          <div className="empty-hero">
            <div className="empty-visual" aria-hidden="true">
              <div className="empty-doc-mark">
                <span className="empty-doc-shadow" />
                <span className="empty-doc-page">
                  <span className="empty-doc-fold" />
                  <span className="empty-doc-rule rule-long" />
                  <span className="empty-doc-rule rule-mid" />
                  <span className="empty-doc-rule rule-short" />
                  <span className="empty-doc-cite cite-one">1</span>
                  <span className="empty-doc-cite cite-two">2</span>
                </span>
              </div>
            </div>

            <div className="empty-copy">
              <p className="empty-eyebrow">Private document chat</p>
              <h2 className="empty-wordmark">Read the source, then ask.</h2>
              <p className="empty-note">
                {hasDocuments ? `${documents.length} document${documents.length > 1 ? 's' : ''} ready in this chat.` : 'Start by attaching a PDF, DOCX, or Markdown file.'}
              </p>
            </div>
          </div>

          <div className="empty-briefing" aria-label="Getting started">
            <div className="briefing-item">
              <FileText size={18} className="briefing-icon" />
              <div>
                <div className="briefing-title">Bring the document</div>
                <div className="briefing-desc">Upload contracts, notes, reports, specs, or research files.</div>
              </div>
            </div>
            <div className="briefing-item">
              <MessageSquareText size={18} className="briefing-icon" />
              <div>
                <div className="briefing-title">Ask like you would ask a colleague</div>
                <div className="briefing-desc">Request summaries, exact clauses, comparisons, or missing details.</div>
              </div>
            </div>
            <div className="briefing-item">
              <ShieldCheck size={18} className="briefing-icon" />
              <div>
                <div className="briefing-title">Keep the chain of evidence</div>
                <div className="briefing-desc">Answers include sources, timings, and the retrieval timeline.</div>
              </div>
            </div>
            <div className="briefing-item">
              <FileKey2 size={18} className="briefing-icon" />
              <div>
                <div className="briefing-title">Bring your API key</div>
                <div className="briefing-desc">Choose a provider, add your key, and select the model you want to use.</div>
              </div>
            </div>
          </div>
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
