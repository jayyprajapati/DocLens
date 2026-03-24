import { useRef, useState } from 'react'
import { Paperclip, SendHorizontal, X } from 'lucide-react'

function InputBar({
  onSend,
  onUpload,
  isSending,
  isUploading,
  documents = [],
  onRemoveDocument = () => {},
  userId = '',
}) {
  const [value, setValue] = useState('')
  const fileInputRef = useRef(null)
  const textareaRef = useRef(null)

  const resizeTextarea = () => {
    const textarea = textareaRef.current
    if (!textarea) {
      return
    }

    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`
  }

  const handleChange = (event) => {
    setValue(event.target.value)
    resizeTextarea()
  }

  const submit = async () => {
    const text = value.trim()
    if (!text || isSending) {
      return
    }

    setValue('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
    await onSend(text)
  }

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  const handleUploadClick = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = async (event) => {
    const [selectedFile] = event.target.files || []
    if (!selectedFile) {
      return
    }

    await onUpload(selectedFile)
    event.target.value = ''
  }

  return (
    <div className="input-bar">
      {documents.length > 0 && (
        <div className="composer-docs" aria-label="Attached documents">
          <div className="composer-docs-title">
            <Paperclip size={14} aria-hidden="true" />
            <span>{documents.length} attachment{documents.length > 1 ? 's' : ''}</span>
          </div>

          <div className="attachment-list">
            {documents.map((document) => (
              <div className="attachment-card" key={document.id}>
                <div className={`attachment-type ${document.typeClassName}`}>{document.typeLabel}</div>
                <div className="attachment-name" title={document.name}>
                  {document.name}
                </div>
                <button
                  type="button"
                  className="attachment-remove"
                  aria-label={`Remove ${document.name}`}
                  onClick={() => onRemoveDocument(document.id)}
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="composer">
        <input
          ref={fileInputRef}
          type="file"
          onChange={handleFileChange}
          className="file-input"
          hidden
        />

        <button
          type="button"
          className="icon-button composer-button"
          onClick={handleUploadClick}
          disabled={isUploading}
          aria-label="Upload document"
          title="Upload document"
        >
          <Paperclip size={16} />
        </button>

        <textarea
          ref={textareaRef}
          value={value}
          rows={1}
          className="chat-input"
          placeholder="Ask something about your docs..."
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          disabled={isSending}
        />

        <button
          type="button"
          className="icon-button composer-button composer-send"
          onClick={submit}
          disabled={isSending || !value.trim()}
          aria-label="Send message"
          title="Send"
        >
          <SendHorizontal size={16} />
        </button>
      </div>

      <div className="composer-meta" aria-live="polite">
        <div className="composer-hint">
          {isUploading
            ? 'Uploading document and preparing retrieval context...'
            : isSending
              ? 'Retrieving relevant chunks and preparing answer...'
              : 'Enter for send message, Shift + Enter for a new line.'}
        </div>
        <div className="composer-user-id" title={userId}>
          User ID: {userId}
        </div>
      </div>
    </div>
  )
}

export default InputBar