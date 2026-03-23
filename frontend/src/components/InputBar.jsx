import { useRef, useState } from 'react'

function InputBar({ onSend, onUpload, isSending, isUploading }) {
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
      <textarea
        ref={textareaRef}
        value={value}
        rows={1}
        className="chat-input"
        placeholder="Ask something about your docs..."
        onChange={handleChange}
        onKeyDown={handleKeyDown}
      />

      <div className="input-actions">
        <input
          ref={fileInputRef}
          type="file"
          onChange={handleFileChange}
          className="file-input"
          hidden
        />

        <button
          type="button"
          className="button"
          onClick={handleUploadClick}
          disabled={isUploading}
        >
          {isUploading ? 'Uploading...' : 'Upload'}
        </button>

        <button type="button" className="button button-primary" onClick={submit} disabled={isSending}>
          {isSending ? 'Sending...' : 'Send'}
        </button>
      </div>
    </div>
  )
}

export default InputBar