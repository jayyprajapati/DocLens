import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import { Bot, Check, Copy, UserRound } from 'lucide-react'

const TYPING_STEP = 2
const TYPING_INTERVAL = 14
const COPY_FEEDBACK_MS = 1400

async function copyToClipboard(text) {
  if (!text) {
    return
  }

  if (navigator?.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }

  const fallbackTextArea = document.createElement('textarea')
  fallbackTextArea.value = text
  fallbackTextArea.setAttribute('readonly', '')
  fallbackTextArea.style.position = 'absolute'
  fallbackTextArea.style.left = '-9999px'
  document.body.appendChild(fallbackTextArea)
  fallbackTextArea.select()
  document.execCommand('copy')
  document.body.removeChild(fallbackTextArea)
}

function getSourceLabel(source, index) {
  if (typeof source === 'string') {
    return source
  }

  const section = source?.section ? `section ${source.section}` : null
  const page = source?.page ? `page ${source.page}` : null
  const docId = source?.doc_id || source?.document || source?.source || null

  return [docId, section, page].filter(Boolean).join(' | ') || `Source ${index + 1}`
}

function MessageBubble({ message }) {
  const isUser = message.role === 'user'
  const isSystem = message.role === 'system'
  const isAssistant = message.role === 'assistant'
  const hasSources = !isUser && Array.isArray(message.sources) && message.sources.length > 0
  const [isCopied, setIsCopied] = useState(false)
  const [typedContent, setTypedContent] = useState(
    isAssistant ? '' : typeof message.content === 'string' ? message.content : '',
  )

  useEffect(() => {
    const content = typeof message.content === 'string' ? message.content : ''

    if (!isAssistant) {
      setTypedContent(content)
      return undefined
    }

    let index = 0
    setTypedContent('')

    const intervalId = window.setInterval(() => {
      index = Math.min(index + TYPING_STEP, content.length)
      setTypedContent(content.slice(0, index))

      if (index >= content.length) {
        window.clearInterval(intervalId)
      }
    }, TYPING_INTERVAL)

    return () => window.clearInterval(intervalId)
  }, [isAssistant, message.content, message.id])

  const isTyping = isAssistant && typedContent.length < (message.content?.length || 0)
  const rawContent = typeof message.content === 'string' ? message.content : ''
  const displayContent = useMemo(() => {
    if (isAssistant) {
      return typedContent
    }

    return typeof message.content === 'string' ? message.content : ''
  }, [isAssistant, message.content, typedContent])

  useEffect(() => {
    if (!isCopied) {
      return undefined
    }

    const timeoutId = window.setTimeout(() => {
      setIsCopied(false)
    }, COPY_FEEDBACK_MS)

    return () => window.clearTimeout(timeoutId)
  }, [isCopied])

  const handleCopy = async () => {
    await copyToClipboard(rawContent)
    setIsCopied(true)
  }

  if (isSystem) {
    const systemTone = message.tone || 'ack'
    return <div className={`system-message system-${systemTone}`}>{message.content}</div>
  }

  const authorName = isUser ? 'You' : 'DocLens'
  const AvatarIcon = isUser ? UserRound : Bot

  return (
    <motion.div
      className={`message-row ${isUser ? 'user' : 'assistant'}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
    >
      {isUser && (
        <div className="message-main user">
          <div className="message-head">
            <span className="message-author">{authorName}</span>
          </div>

          <div className={`message-bubble ${isUser ? 'user' : 'assistant'}`}>
            <p>{displayContent}</p>
          </div>

          <div className="message-actions user">
            <button type="button" className="message-copy" onClick={handleCopy}>
              {isCopied ? (
                <>
                  <Check size={14} />
                  <span>Copied</span>
                </>
              ) : (
                <>
                  <Copy size={14} />
                  <span>Copy</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

      <div className={`message-avatar ${isUser ? 'user' : 'assistant'}`} aria-hidden="true">
        <AvatarIcon size={16} />
      </div>

      {isAssistant && (
        <div className="message-main assistant">
          <div className="message-head">
            <span className="message-author">{authorName}</span>
          </div>

          <div className={`message-bubble ${isUser ? 'user' : 'assistant'}`}>
            <ReactMarkdown>{displayContent}</ReactMarkdown>
            {isTyping && <span className="typing-cursor" aria-hidden="true" />}

            {hasSources && !isTyping && (
              <div className="message-sources">
                <div className="sources-title">Sources</div>
                <ul>
                  {message.sources.map((source, index) => (
                    <li key={`${getSourceLabel(source, index)}-${index}`}>
                      {getSourceLabel(source, index)}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div className="message-actions assistant">
            <button type="button" className="message-copy" onClick={handleCopy}>
              {isCopied ? (
                <>
                  <Check size={14} />
                  <span>Copied</span>
                </>
              ) : (
                <>
                  <Copy size={14} />
                  <span>Copy</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </motion.div>
  )
}

export default MessageBubble