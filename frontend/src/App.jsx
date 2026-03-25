import { useEffect, useState } from 'react'
import { v4 as uuidv4 } from 'uuid'
import Header from './components/Header'
import ChatWindow from './components/ChatWindow'
import InputBar from './components/InputBar'
import InfoModal from './components/InfoModal'
import { deleteAllDocuments, deleteDocument, ingest, query } from './services/api'
import './App.css'

const STORAGE_KEYS = {
  userId: 'doclens_user_id',
  apiKey: 'doclens_api_key',
  model: 'doclens_model',
}

const DEFAULT_MODEL = ''
const FREE_LIMITS = { docs: 1, queries: 2 }
const BYOK_LIMITS = { docs: 5, queries: null }

function getFallbackLimits(apiKey) {
  return apiKey?.trim() ? BYOK_LIMITS : FREE_LIMITS
}

function getInitialUsage(apiKey) {
  return {
    docs: 0,
    queries: 0,
    limits: getFallbackLimits(apiKey),
  }
}

function getUsageFromPayload(payload) {
  if (!payload || typeof payload !== 'object' || !payload.usage || typeof payload.usage !== 'object') {
    return null
  }

  return payload.usage
}

function waitForNextFrame() {
  return new Promise((resolve) => {
    requestAnimationFrame(() => resolve())
  })
}

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

function getDocumentIdFromIngestResponse(payload) {
  if (!payload || typeof payload !== 'object') {
    return null
  }

  const nestedResult = payload.result && typeof payload.result === 'object' ? payload.result : null
  const candidates = [
    payload.doc_id,
    payload.document_id,
    payload.id,
    nestedResult?.doc_id,
    nestedResult?.document_id,
    nestedResult?.id,
  ]

  const docId = candidates.find((candidate) => typeof candidate === 'string' && candidate.trim())
  return docId || null
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
  const [model, setModel] = useState(() => {
    const storedModel = localStorage.getItem(STORAGE_KEYS.model)
    if (!storedModel || storedModel === 'gpt-4o-mini') {
      return DEFAULT_MODEL
    }

    return storedModel
  })
  const [chat, setChat] = useState([])
  const [documents, setDocuments] = useState([])
  const [loadingState, setLoadingState] = useState('idle')
  const [loadingTask, setLoadingTask] = useState('query')
  const [usage, setUsage] = useState(() => getInitialUsage(localStorage.getItem(STORAGE_KEYS.apiKey) || ''))
  const [inlineFeedback, setInlineFeedback] = useState(null)
  const [documentPendingDeletion, setDocumentPendingDeletion] = useState(null)
  const [isDeletingDocument, setIsDeletingDocument] = useState(false)

  const inputLocked = loadingState !== 'idle'

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.apiKey, apiKey)
  }, [apiKey])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.model, model)
  }, [model])

  useEffect(() => {
    setUsage((previousUsage) => ({
      ...previousUsage,
      limits: getFallbackLimits(apiKey),
    }))
  }, [apiKey])

  const addMessage = (message) => {
    setChat((previousMessages) => [...previousMessages, message])
  }

  const updateUsage = (payload) => {
    const usagePayload = getUsageFromPayload(payload)
    if (!usagePayload) {
      return
    }

    setUsage((previousUsage) => {
      const nextDocs = Number.isFinite(Number(usagePayload.docs))
        ? Number(usagePayload.docs)
        : previousUsage.docs
      const nextQueries = Number.isFinite(Number(usagePayload.queries))
        ? Number(usagePayload.queries)
        : previousUsage.queries

      const nextLimits = usagePayload.limits && typeof usagePayload.limits === 'object'
        ? {
            docs: usagePayload.limits.docs ?? getFallbackLimits(apiKey).docs,
            queries:
              usagePayload.limits.queries === undefined
                ? getFallbackLimits(apiKey).queries
                : usagePayload.limits.queries,
          }
        : previousUsage.limits

      return {
        docs: nextDocs,
        queries: nextQueries,
        limits: nextLimits,
      }
    })
  }

  const handleSend = async (text) => {
    if (!text.trim() || inputLocked) {
      return
    }

    setInlineFeedback(null)

    addMessage({
      id: uuidv4(),
      role: 'user',
      content: text,
    })

    setLoadingTask('query')
    setLoadingState('retrieving')

    try {
      const result = await query(text, userId, apiKey, model)
      updateUsage(result)

      const generationTimeMs = Number(result?.meta?.generation_time)
      if (Number.isFinite(generationTimeMs) && generationTimeMs > 0) {
        setLoadingState('generating')
        await waitForNextFrame()
      }

      addMessage({
        id: uuidv4(),
        role: 'assistant',
        content:
          result?.answer || result?.response || result?.message || 'No response returned.',
        sources: Array.isArray(result?.sources) ? result.sources : [],
      })
    } catch (error) {
      updateUsage(error?.payload)

      if (error?.code === 'QUOTA_EXCEEDED') {
        const quotaMessage = "You've reached your free limit. Add your API key to continue."
        setInlineFeedback({ tone: 'warning', content: quotaMessage })
        addMessage({
          id: uuidv4(),
          role: 'system',
          tone: 'warning',
          content: quotaMessage,
        })
        return
      }

      addMessage({
        id: uuidv4(),
        role: 'system',
        tone: 'error',
        content: `Could not complete your request. ${parseErrorMessage(error?.message)}`,
      })
    } finally {
      setLoadingState('idle')
      setLoadingTask('query')
    }
  }

  const handleUpload = async (file) => {
    if (!file || inputLocked) {
      return
    }

    setInlineFeedback(null)
    setLoadingTask('upload')
    setLoadingState('retrieving')

    try {
      const ingestResult = await ingest(file, userId, apiKey)
      updateUsage(ingestResult)
      const docId = getDocumentIdFromIngestResponse(ingestResult)

      if (!docId) {
        throw new Error('Upload response missing document identifier.')
      }

      const typeMeta = getDocumentTypeMeta(file.name)
      setDocuments((previousDocuments) => [
        ...previousDocuments,
        {
          id: uuidv4(),
          doc_id: docId,
          name: file.name,
          status: 'uploaded',
          typeLabel: typeMeta.label,
          typeClassName: typeMeta.className,
        },
      ])

      addMessage({
        id: uuidv4(),
        role: 'system',
        tone: 'success',
        content: 'Document uploaded successfully',
      })
    } catch (error) {
      updateUsage(error?.payload)

      if (error?.code === 'QUOTA_EXCEEDED') {
        const uploadLimitMessage = 'Upload limit reached (1 free / 5 with API key)'
        setInlineFeedback({ tone: 'warning', content: uploadLimitMessage })
        addMessage({
          id: uuidv4(),
          role: 'system',
          tone: 'warning',
          content: uploadLimitMessage,
        })
        return
      }

      addMessage({
        id: uuidv4(),
        role: 'system',
        tone: 'error',
        content: `Upload failed. ${toPlainLanguageUploadError(error?.message)}`,
      })
    } finally {
      setLoadingState('idle')
      setLoadingTask('query')
    }
  }

  const handleReset = async () => {
    try {
      await deleteAllDocuments(userId, apiKey)
    } catch (error) {
      addMessage({
        id: uuidv4(),
        role: 'system',
        tone: 'warning',
        content: `Reset warning: remote cleanup did not fully complete. ${parseErrorMessage(error?.message)}`,
      })
    }

    localStorage.clear()
    const newUserId = uuidv4()
    localStorage.setItem(STORAGE_KEYS.userId, newUserId)
    setUserId(newUserId)
    setApiKey('')
    setModel(DEFAULT_MODEL)
    setChat([])
    setDocuments([])
    setDocumentPendingDeletion(null)
    setUsage(getInitialUsage(''))
    setInlineFeedback(null)
    setLoadingState('idle')
    setLoadingTask('query')
  }

  const handleRequestRemoveDocument = (document) => {
    if (!document?.doc_id) {
      console.error('Delete blocked: missing doc_id for document', document)
      addMessage({
        id: uuidv4(),
        role: 'system',
        tone: 'error',
        content: 'Failed to delete document. Please try again.',
      })
      return
    }

    setDocumentPendingDeletion(document)
  }

  const handleConfirmRemoveDocument = async () => {
    if (!documentPendingDeletion || isDeletingDocument) {
      return
    }

    if (!documentPendingDeletion.doc_id) {
      console.error('Delete blocked: missing doc_id for pending deletion', documentPendingDeletion)
      addMessage({
        id: uuidv4(),
        role: 'system',
        tone: 'error',
        content: 'Failed to delete document. Please try again.',
      })
      setDocumentPendingDeletion(null)
      return
    }

    setIsDeletingDocument(true)
    try {
      await deleteDocument(userId, documentPendingDeletion.doc_id, apiKey)
      setDocuments((previousDocuments) =>
        previousDocuments.filter((document) => document.id !== documentPendingDeletion.id),
      )
      addMessage({
        id: uuidv4(),
        role: 'system',
        tone: 'success',
        content: `Document deleted: ${documentPendingDeletion.name}`,
      })
    } catch (error) {
      addMessage({
        id: uuidv4(),
        role: 'system',
        tone: 'error',
        content: 'Failed to delete document. Please try again.',
      })
    } finally {
      setIsDeletingDocument(false)
      setDocumentPendingDeletion(null)
    }
  }

  const hasConversation = chat.length > 0

  return (
    <div className="app-page">
      <div className="app-shell">
        <Header
          apiKey={apiKey}
          model={model}
          usage={usage}
          onApiKeyChange={setApiKey}
          onModelChange={setModel}
          onReset={handleReset}
        />
        <ChatWindow
          messages={chat}
          loadingState={loadingState}
          loadingTask={loadingTask}
        />
        <InputBar
          onSend={handleSend}
          onUpload={handleUpload}
          isLocked={inputLocked}
          loadingState={loadingState}
          loadingTask={loadingTask}
          documents={documents}
          onRequestRemoveDocument={handleRequestRemoveDocument}
          userId={userId}
        />

        {inlineFeedback && (
          <div className={`inline-feedback inline-feedback-${inlineFeedback.tone}`} role="status" aria-live="polite">
            {inlineFeedback.content}
          </div>
        )}

        {hasConversation && (
          <div className="constraints-inline">
            {usage.limits?.queries == null
              ? `Docs: ${usage.docs} / ${usage.limits?.docs ?? 5} • Queries: unlimited`
              : `Docs: ${usage.docs} / ${usage.limits?.docs ?? 1} • Queries: ${usage.queries} / ${usage.limits?.queries ?? 2}`}
          </div>
        )}

        <InfoModal
          isOpen={Boolean(documentPendingDeletion)}
          onClose={() => {
            if (!isDeletingDocument) {
              setDocumentPendingDeletion(null)
            }
          }}
          title="Delete document"
          footer={
            <button
              type="button"
              className="button button-danger"
              onClick={handleConfirmRemoveDocument}
              disabled={isDeletingDocument}
            >
              {isDeletingDocument ? 'Deleting...' : 'Delete permanently'}
            </button>
          }
        >
          <p>This will permanently delete your document. Continue?</p>
          {documentPendingDeletion?.name && <p><strong>{documentPendingDeletion.name}</strong></p>}
        </InfoModal>
      </div>
    </div>
  )
}

export default App
