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
        role: 'assistant',
        content: `Request failed: ${error.message}`,
        sources: [],
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
    try {
      await ingest(file, userId)
      addMessage({
        id: uuidv4(),
        role: 'assistant',
        content: `Uploaded **${file.name}** successfully.`,
        sources: [],
      })
    } catch (error) {
      addMessage({
        id: uuidv4(),
        role: 'assistant',
        content: `Upload failed for **${file.name}**: ${error.message}`,
        sources: [],
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
  }

  return (
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
      />
      <div className="session-id">Session: {userId}</div>
    </div>
  )
}

export default App
