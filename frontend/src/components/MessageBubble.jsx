import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import { Bot, Check, Copy, FileText, Search, UserRound, X } from 'lucide-react'

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

const MAX_SECTION_LEN = 52

function formatSection(raw) {
  if (!raw || typeof raw !== 'string') return 'Untitled'
  // Take only the first line — section names from parsed PDFs often run long
  const firstLine = raw.split(/[\n\r]/)[0].trim()
  return firstLine.length > MAX_SECTION_LEN
    ? `${firstLine.slice(0, MAX_SECTION_LEN - 1)}…`
    : firstLine || 'Untitled'
}

function getSourceKey(source) {
  const section = typeof source?.section === 'string' ? source.section.trim() : ''
  const page = source?.page ?? ''
  return `${section}||${page}`
}

function deduplicateSources(sources) {
  const seen = new Set()
  return sources.filter((s) => {
    const key = getSourceKey(s)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function StageIcon({ status }) {
  if (status === 'done')  return <span className="tl-dot tl-done"  aria-hidden="true">✓</span>
  if (status === 'error') return <span className="tl-dot tl-error" aria-hidden="true"><X size={10} /></span>
  if (status === 'active') return <span className="tl-dot tl-active" aria-hidden="true"><span className="tl-pulse" /></span>
  return <span className="tl-dot tl-pending" aria-hidden="true" />
}

function TimelineMessage({ message }) {
  const { operation, filename, query, stages = [], result, error } = message
  const Icon = operation === 'upload' ? FileText : Search
  const isComplete = result !== null
  const hasFailed  = Boolean(error)

  const headerLabel = operation === 'upload'
    ? (filename || 'File upload')
    : (query ? `"${query.length > 60 ? query.slice(0, 58) + '…' : query}"` : 'Query')

  return (
    <motion.div
      className="tl-card"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
    >
      <div className="tl-header">
        <Icon size={13} className="tl-header-icon" aria-hidden="true" />
        <span className="tl-header-label">{headerLabel}</span>
        {isComplete && !hasFailed && <span className="tl-badge tl-badge-ok">Done</span>}
        {hasFailed && <span className="tl-badge tl-badge-err">Failed</span>}
      </div>

      <ol className="tl-stages" aria-label="Pipeline stages">
        {stages.map((stage) => (
          <li key={stage.id} className={`tl-stage tl-stage-${stage.status}`}>
            <StageIcon status={stage.status} />
            <span className="tl-stage-label">{stage.label}</span>
          </li>
        ))}
      </ol>

      {isComplete && !hasFailed && result && (
        <div className="tl-result">
          {operation === 'upload' && result.chunk_count != null && (
            <span>{result.chunk_count} chunks indexed</span>
          )}
          {operation === 'query' && (
            <>
              {result.retrieved != null && (
                <span>{result.retrieved} retrieved → {result.reranked ?? result.source_count} ranked</span>
              )}
              {result.retrieve_ms != null && (
                <span>{Math.round(result.retrieve_ms + (result.generate_ms ?? 0))} ms total</span>
              )}
            </>
          )}
        </div>
      )}

      {hasFailed && (
        <div className="tl-error-msg">{error}</div>
      )}
    </motion.div>
  )
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

  if (message.role === 'timeline') {
    return <TimelineMessage message={message} />
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
                  {deduplicateSources(message.sources).map((source, index) => {
                    const section = formatSection(source?.section)
                    const page = source?.page != null ? `p.${source.page}` : null
                    return (
                      <li key={`${section}--${page}--${index}`}>
                        <span className="source-section">{section}</span>
                        {page && <span className="source-page">{page}</span>}
                      </li>
                    )
                  })}
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