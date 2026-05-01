import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import { Bot, Check, Copy, FileText, Search, UserRound } from 'lucide-react'

const TYPING_STEP = 3
const TYPING_INTERVAL = 12
const COPY_FEEDBACK_MS = 1400
const MAX_SECTION_LEN = 48

// ─── helpers ────────────────────────────────────────────────────────────────

async function copyToClipboard(text) {
  if (!text) return
  if (navigator?.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.setAttribute('readonly', '')
  ta.style.cssText = 'position:absolute;left:-9999px'
  document.body.appendChild(ta)
  ta.select()
  document.execCommand('copy')
  document.body.removeChild(ta)
}

function formatSection(raw) {
  if (!raw || typeof raw !== 'string') return 'Untitled'
  const first = raw.split(/[\n\r]/)[0].trim()
  return first.length > MAX_SECTION_LEN ? `${first.slice(0, MAX_SECTION_LEN - 1)}…` : first || 'Untitled'
}

function getSourceKey(source) {
  return `${(source?.section || '').trim()}||${source?.page ?? ''}`
}

function deduplicateSources(sources) {
  const seen = new Set()
  return sources.filter((s) => {
    const k = getSourceKey(s)
    if (seen.has(k)) return false
    seen.add(k)
    return true
  })
}

// ─── sub-components ─────────────────────────────────────────────────────────

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const t = setTimeout(() => setCopied(false), COPY_FEEDBACK_MS)
    return () => clearTimeout(t)
  }, [copied])
  return (
    <button
      type="button"
      className="msg-copy"
      onClick={async () => { await copyToClipboard(text); setCopied(true) }}
      aria-label={copied ? 'Copied' : 'Copy to clipboard'}
    >
      {copied ? <><Check size={12} /><span>Copied</span></> : <><Copy size={12} /><span>Copy</span></>}
    </button>
  )
}

function SourceList({ sources }) {
  const deduped = deduplicateSources(sources)
  if (!deduped.length) return null
  return (
    <div className="src-list" aria-label="Sources">
      <div className="src-label">Sources</div>
      <ul className="src-ul">
        {deduped.map((s, i) => {
          const section = formatSection(s?.section)
          const page = s?.page != null ? `p.${s.page}` : null
          return (
            <li key={`${section}--${i}`} className="src-item">
              {section}{page && <span className="src-page"> · {page}</span>}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

// Typing animation for the embedded answer inside a timeline thread
function AnswerBlock({ answer, sources, retrieveMs, generateMs }) {
  const [typed, setTyped] = useState('')

  useEffect(() => {
    if (!answer) return
    let i = 0
    setTyped('')
    const iv = setInterval(() => {
      i = Math.min(i + TYPING_STEP, answer.length)
      setTyped(answer.slice(0, i))
      if (i >= answer.length) clearInterval(iv)
    }, TYPING_INTERVAL)
    return () => clearInterval(iv)
  }, [answer])

  const isTyping = typed.length < (answer?.length || 0)
  const totalSecs = retrieveMs != null || generateMs != null
    ? (((retrieveMs || 0) + (generateMs || 0)) / 1000).toFixed(1)
    : null

  return (
    <div className="tl-answer-body">
      <ReactMarkdown>{typed}</ReactMarkdown>
      {isTyping && <span className="typing-cursor" aria-hidden="true" />}
      {!isTyping && sources?.length > 0 && <SourceList sources={sources} />}
      {!isTyping && answer && (
        <div className="tl-answer-footer">
          {totalSecs && <span className="tl-answered-in">Answered in {totalSecs}s</span>}
          <CopyButton text={answer} />
        </div>
      )}
    </div>
  )
}

// ─── Timeline knot ──────────────────────────────────────────────────────────

function Knot({ status }) {
  return <span className={`tl-knot tl-knot-${status}`} aria-hidden="true" />
}

// ─── Timeline (thread design) ───────────────────────────────────────────────

function TimelineMessage({ message }) {
  const { operation, filename, query, stages = [], result, error } = message
  const Icon = operation === 'upload' ? FileText : Search

  const headerText = operation === 'upload'
    ? (filename || 'Upload')
    : (query ? (query.length > 72 ? `${query.slice(0, 70)}…` : query) : 'Query')

  const hasAnswer       = operation === 'query' && result?.answer
  const hasUploadResult = operation === 'upload' && result
  const hasFailed       = Boolean(error)

  return (
    <motion.div
      className="tl-thread"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
    >
      {/* Operation header */}
      <div className="tl-thread-header">
        <Icon size={13} className="tl-header-icon" aria-hidden="true" />
        <span className="tl-header-text">{headerText}</span>
      </div>

      {/* Stage rows */}
      {stages.map((stage, idx) => {
        const isLast = idx === stages.length - 1
        const showLine = !isLast || hasAnswer || hasUploadResult || hasFailed
        const timeLabel = stage.status === 'done' && stage.elapsedMs != null
          ? ` (${stage.elapsedMs}ms)`
          : ''
        return (
          <div key={stage.id} className="tl-row">
            <div className="tl-rail">
              <Knot status={stage.status} />
              {showLine && <span className="tl-line" aria-hidden="true" />}
            </div>
            <div className="tl-stage-content">
              <span className={`tl-stage-label tl-stage-${stage.status}`}>
                {stage.label}
                {timeLabel && <span className="tl-stage-time">{timeLabel}</span>}
              </span>
            </div>
          </div>
        )
      })}

      {/* Upload completion node */}
      {hasUploadResult && !hasFailed && (
        <div className="tl-row">
          <div className="tl-rail">
            <Knot status="done" />
          </div>
          <div className="tl-stage-content tl-complete-row">
            {result.chunk_count != null
              ? <span className="tl-complete-text">{result.chunk_count} chunks indexed — ready to query</span>
              : <span className="tl-complete-text">Indexed successfully</span>}
          </div>
        </div>
      )}

      {/* Answer node (query only) */}
      {hasAnswer && (
        <div className="tl-row tl-answer-row">
          <div className="tl-rail">
            <Knot status="answer" />
          </div>
          <div className="tl-stage-content">
            <AnswerBlock
              answer={result.answer}
              sources={result.sources}
              retrieveMs={result.retrieve_ms}
              generateMs={result.generate_ms}
            />
          </div>
        </div>
      )}

      {/* Error node */}
      {hasFailed && (
        <div className="tl-row">
          <div className="tl-rail">
            <Knot status="error" />
          </div>
          <div className="tl-stage-content">
            <span className="tl-error-text">{error}</span>
          </div>
        </div>
      )}
    </motion.div>
  )
}

// ─── Doc-select message ──────────────────────────────────────────────────────

function DocSelectMessage({ message, onDocSelect }) {
  const { query, documents = [] } = message
  return (
    <motion.div
      className="doc-select-msg"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
    >
      <p className="doc-select-prompt">Multiple documents found. Which one are you asking about?</p>
      <div className="doc-select-buttons">
        {documents.map((doc) => (
          <button
            key={doc.id}
            type="button"
            className="doc-select-btn"
            onClick={() => onDocSelect && onDocSelect(doc.doc_id, doc.name, query)}
          >
            <span className={`attachment-type ${doc.typeClassName}`} style={{ fontSize: '9px', padding: '2px 4px', borderRadius: '3px', color: '#fff', fontWeight: 700, letterSpacing: '0.04em', marginRight: '6px' }}>
              {doc.typeLabel}
            </span>
            {doc.name}
          </button>
        ))}
      </div>
    </motion.div>
  )
}

// ─── Main MessageBubble ──────────────────────────────────────────────────────

function MessageBubble({ message, onDocSelect }) {
  const isUser      = message.role === 'user'
  const isSystem    = message.role === 'system'
  const isAssistant = message.role === 'assistant'
  const isTimeline  = message.role === 'timeline'
  const isDocSelect = message.role === 'doc-select'
  const hasSources  = isAssistant && Array.isArray(message.sources) && message.sources.length > 0

  const [typedContent, setTypedContent] = useState(
    isAssistant ? '' : typeof message.content === 'string' ? message.content : '',
  )

  useEffect(() => {
    const content = typeof message.content === 'string' ? message.content : ''
    if (!isAssistant) { setTypedContent(content); return }
    let i = 0
    setTypedContent('')
    const iv = setInterval(() => {
      i = Math.min(i + TYPING_STEP, content.length)
      setTypedContent(content.slice(0, i))
      if (i >= content.length) clearInterval(iv)
    }, TYPING_INTERVAL)
    return () => clearInterval(iv)
  }, [isAssistant, message.content, message.id])

  const isTyping = isAssistant && typedContent.length < (message.content?.length || 0)
  const displayContent = useMemo(() => {
    if (isAssistant) return typedContent
    return typeof message.content === 'string' ? message.content : ''
  }, [isAssistant, message.content, typedContent])

  if (isTimeline)  return <TimelineMessage message={message} />
  if (isDocSelect) return <DocSelectMessage message={message} onDocSelect={onDocSelect} />

  if (isSystem) {
    const tone = message.tone || 'ack'
    return <div className={`sys-msg sys-${tone}`}>{message.content}</div>
  }

  const rawContent = typeof message.content === 'string' ? message.content : ''

  return (
    <motion.div
      className={`msg-row ${isUser ? 'msg-user' : 'msg-assistant'}`}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
    >
      {!isUser && (
        <div className="msg-avatar msg-avatar-assistant" aria-hidden="true">
          <Bot size={14} />
        </div>
      )}

      <div className={`msg-body ${isUser ? 'msg-body-user' : 'msg-body-assistant'}`}>
        <div className={`msg-bubble ${isUser ? 'bubble-user' : 'bubble-assistant'}`}>
          {isUser
            ? <p>{displayContent}</p>
            : <ReactMarkdown>{displayContent}</ReactMarkdown>}
          {isTyping && <span className="typing-cursor" aria-hidden="true" />}
          {isAssistant && hasSources && !isTyping && <SourceList sources={message.sources} />}
        </div>
        <CopyButton text={rawContent} />
      </div>

      {isUser && (
        <div className="msg-avatar msg-avatar-user" aria-hidden="true">
          <UserRound size={14} />
        </div>
      )}
    </motion.div>
  )
}

export default MessageBubble
