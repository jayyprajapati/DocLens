import { useEffect, useRef } from 'react'
import { BookOpen, FileSearch, FileText, KeyRound, MessageSquare } from 'lucide-react'
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
            <span className="empty-hero-icon" aria-hidden="true">
              <FileSearch size={28} strokeWidth={1.75} />
            </span>
            <div className="empty-hero-copy">
              <h2 className="empty-app-name">
                <span className="empty-title-line">DocLens,</span>
                <span className="empty-title-highlight">answers drawn straight.</span>
              </h2>
              <p className="empty-tagline">
                {hasDocuments
                  ? `${documents.length} document${documents.length > 1 ? 's' : ''} attached — ask anything below.`
                  : 'Upload documents. Ask questions. Get cited answers.'}
              </p>
            </div>
          </div>

          {hasDocuments ? (
            <div className="empty-docs-ready">
              Your documents are ready. Type a question below to get started.
            </div>
          ) : (
            <>
              <div className="empty-feature-grid">
                <div className="empty-feature-card">
                  <span className="empty-feature-icon">
                    <FileText size={19} aria-hidden="true" />
                  </span>
                  <div className="empty-feature-copy">
                    <div className="empty-feature-title">Upload your documents</div>
                    <div className="empty-feature-desc">
                      PDF, DOCX, or Markdown. Attach per-chat with the paperclip or add to Resources to share across all conversations.
                    </div>
                  </div>
                </div>

                <div className="empty-feature-card">
                  <span className="empty-feature-icon">
                    <MessageSquare size={19} aria-hidden="true" />
                  </span>
                  <div className="empty-feature-copy">
                    <div className="empty-feature-title">Ask in plain language</div>
                    <div className="empty-feature-desc">
                      Summarize a contract, extract clauses, compare sections — the same way you'd ask a colleague.
                    </div>
                  </div>
                </div>

                <div className="empty-feature-card">
                  <span className="empty-feature-icon">
                    <BookOpen size={19} aria-hidden="true" />
                  </span>
                  <div className="empty-feature-copy">
                    <div className="empty-feature-title">Every answer is cited</div>
                    <div className="empty-feature-desc">
                      Each response includes the exact page, section, and passage it came from. Tap any marker to verify inline.
                    </div>
                  </div>
                </div>

                <div className="empty-feature-card">
                  <span className="empty-feature-icon">
                    <KeyRound size={19} aria-hidden="true" />
                  </span>
                  <div className="empty-feature-copy">
                    <div className="empty-feature-title">Bring your own key</div>
                    <div className="empty-feature-desc">
                      BYOK — choose OpenAI, Claude, or Ollama Cloud. Your key stays in your browser and never touches DocLens servers.
                    </div>
                  </div>
                </div>
              </div>

              <div className="empty-cta">
                Use the <strong>paperclip</strong> icon to attach a file to this chat, or open <strong>Resources</strong> in the sidebar to upload files shared across all chats.
              </div>
            </>
          )}
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
