import ReactMarkdown from 'react-markdown'

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
  const hasSources = !isUser && Array.isArray(message.sources) && message.sources.length > 0

  return (
    <div className={`message-row ${isUser ? 'user' : 'assistant'}`}>
      <div className={`message-bubble ${isUser ? 'user' : 'assistant'}`}>
        {isUser ? <p>{message.content}</p> : <ReactMarkdown>{message.content}</ReactMarkdown>}

        {hasSources && (
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
    </div>
  )
}

export default MessageBubble