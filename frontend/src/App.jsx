import { useEffect, useState } from 'react'
import { v4 as uuidv4 } from 'uuid'
import Header from './components/Header'
import ChatWindow from './components/ChatWindow'
import InputBar from './components/InputBar'
import { ingest, query } from './services/api'
import './App.css'

const STORAGE_KEYS = {
  userId: 'doclens_user_id',
  apiKey: 'doclens_api_key',
  model: 'doclens_model',
}

const DEFAULT_MODEL = 'gpt-4o-mini'

function parseErrorMessage(rawMessage) {
  if (!rawMessage) {
    return 'Something went wrong. Please try again.'
  }

  const trimmedMessage = String(rawMessage).trim()

  if (trimmedMessage.startsWith('{') && trimmedMessage.endsWith('}')) {
    try {
      const parsed = JSON.parse(trimmedMessage)
      if (typeof parsed?.detail === 'string' && parsed.detail.trim()) {
        return parsed.detail.trim()
      }
    } catch {
      return trimmedMessage
    }
  }

  return trimmedMessage
}

function toPlainLanguageUploadError(rawMessage) {
  const message = parseErrorMessage(rawMessage)
  const lowerMessage = message.toLowerCase()

  if (lowerMessage.includes('free document limit exceeded')) {
    return 'You reached the free upload limit (1 document). Add your API key to upload more files.'
  }

  if (lowerMessage.includes('api key')) {
    return 'Upload requires an API key for this request. Add your key and try again.'
  }

  return message
}

function getDocumentTypeMeta(fileName) {
  const extension = fileName?.split('.').pop()?.toLowerCase()

  if (extension === 'pdf') {
    return { label: 'PDF', className: 'type-pdf' }
  }

  if (extension === 'docx' || extension === 'doc') {
    return { label: 'DOCX', className: 'type-docx' }
  }

  if (extension === 'md' || extension === 'markdown') {
    return { label: '.MD', className: 'type-md' }
  }

  return { label: 'FILE', className: 'type-generic' }
}

function getOrCreateUserId() {
  const existingUserId = localStorage.getItem(STORAGE_KEYS.userId)
  if (existingUserId) {
    return existingUserId
  }

  const newUserId = uuidv4()
  localStorage.setItem(STORAGE_KEYS.userId, newUserId)
  return newUserId
}

function App() {
  const [userId, setUserId] = useState(() => getOrCreateUserId())
  const [apiKey, setApiKey] = useState(
    () => localStorage.getItem(STORAGE_KEYS.apiKey) || '',
  )
  const [model, setModel] = useState(
    () => localStorage.getItem(STORAGE_KEYS.model) || DEFAULT_MODEL,
  )
  const [messages, setMessages] = useState([])
  const [documents, setDocuments] = useState([])
  const [isSending, setIsSending] = useState(false)
  const [isUploading, setIsUploading] = useState(false)

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.apiKey, apiKey)
  }, [apiKey])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.model, model)
  }, [model])

  const addMessage = (message) => {
    setMessages((previousMessages) => [...previousMessages, message])
  }

  const handleSend = async (text) => {
    if (!text.trim() || isSending) {
      return
    }

    addMessage({
      id: uuidv4(),
      role: 'user',
      content: text,
    })

    addMessage({
      id: uuidv4(),
      role: 'system',
      tone: 'ack',
      content: 'Processing your question...'
    })

    setIsSending(true)
    try {
      const result = await query(text, userId, apiKey, model)
      addMessage({
        id: uuidv4(),
        role: 'assistant',
        content:
          result?.answer || result?.response || result?.message || 'No response returned.',
        sources: Array.isArray(result?.sources) ? result.sources : [],
      })
    } catch (error) {
      addMessage({
        id: uuidv4(),
        role: 'system',
        tone: 'error',
        content: `Could not complete your request. ${parseErrorMessage(error?.message)}`,
      })
    } finally {
      setIsSending(false)
    }
  }

  const handleUpload = async (file) => {
    if (!file || isUploading) {
      return
    }

    setIsUploading(true)
    addMessage({
      id: uuidv4(),
      role: 'system',
      tone: 'ack',
      content: 'Uploading and processing your document...'
    })

    try {
      await ingest(file, userId)

      const typeMeta = getDocumentTypeMeta(file.name)
      setDocuments((previousDocuments) => [
        ...previousDocuments,
        {
          id: uuidv4(),
          name: file.name,
          typeLabel: typeMeta.label,
          typeClassName: typeMeta.className,
        },
      ])

      addMessage({
        id: uuidv4(),
        role: 'system',
        tone: 'success',
        content: `Uploaded successfully: ${file.name}`,
      })
    } catch (error) {
      addMessage({
        id: uuidv4(),
        role: 'system',
        tone: 'error',
        content: `Upload failed. ${toPlainLanguageUploadError(error?.message)}`,
      })
    } finally {
      setIsUploading(false)
    }
  }

  const handleReset = () => {
    localStorage.clear()
    const newUserId = uuidv4()
    localStorage.setItem(STORAGE_KEYS.userId, newUserId)
    setUserId(newUserId)
    setApiKey('')
    setModel(DEFAULT_MODEL)
    setMessages([])
    setDocuments([])
  }

  const handleRemoveDocument = (documentId) => {
    setDocuments((previousDocuments) =>
      previousDocuments.filter((document) => document.id !== documentId),
    )
  }

  const hasConversation = messages.length > 0

  return (
    <div className="app-page">
      <div className="app-shell">
        <Header
          apiKey={apiKey}
          model={model}
          onApiKeyChange={setApiKey}
          onModelChange={setModel}
          onReset={handleReset}
        />
        <ChatWindow messages={messages} isSending={isSending} />
        <InputBar
          onSend={handleSend}
          onUpload={handleUpload}
          isSending={isSending}
          isUploading={isUploading}
          documents={documents}
          onRemoveDocument={handleRemoveDocument}
          userId={userId}
        />

        {hasConversation && (
          <div className="constraints-inline">
            Free usage limits: max 2 queries, max 1 document, max 3 pages.
          </div>
        )}
      </div>
    </div>
  )
}

export default App
