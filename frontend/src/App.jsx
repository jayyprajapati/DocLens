import { useEffect, useRef, useState } from 'react'
import { v4 as uuidv4 } from 'uuid'
import Header from './components/Header'
import ChatWindow from './components/ChatWindow'
import InputBar from './components/InputBar'
import InfoModal from './components/InfoModal'
import AppFooter from './components/AppFooter'
import { deleteAllDocuments, deleteDocument, getDocuments, ingest, query } from './services/api'
import './App.css'

const STORAGE_KEYS = {
  userId: 'doclens_user_id',
  apiKey: 'doclens_api_key',
  selectedModel: 'doclens_selected_model',
  provider: 'doclens_provider',
}

// Stage definitions — progress through these on a timer while waiting for the API
const UPLOAD_STAGES = [
  { id: 'receiving',  label: 'Receiving file' },
  { id: 'parsing',    label: 'Parsing document' },
  { id: 'embedding',  label: 'Generating embeddings' },
  { id: 'storing',    label: 'Storing vectors' },
]

const QUERY_STAGES = [
  { id: 'embedding',   label: 'Embedding query' },
  { id: 'searching',   label: 'Searching documents' },
  { id: 'reranking',   label: 'Re-ranking results' },
  { id: 'generating',  label: 'Generating answer' },
]

// Approx ms to spend on each stage before advancing (purely cosmetic pacing)
const UPLOAD_PACE = [300, 800, 1400, 600]
const QUERY_PACE  = [250, 500, 400, 300]

function buildStages(defs) {
  return defs.map((s, i) => ({ ...s, status: i === 0 ? 'active' : 'pending', detail: null }))
}

function getByokValidationMessage(apiKey, selectedModel, provider) {
  const hasApiKey  = Boolean(apiKey.trim())
  const hasModel   = Boolean(selectedModel.trim())
  const hasProvider = Boolean(provider.trim())
  if (hasApiKey && hasModel && hasProvider) return ''
  const missing = []
  if (!hasProvider) missing.push('provider')
  if (!hasApiKey)   missing.push('API key')
  if (!hasModel)    missing.push('model')
  if (missing.length === 3) return 'Select a provider, add your API key, and select a model to continue.'
  return `Add your ${missing.join(' and ')} to continue.`
}

function getDocumentTypeMeta(fileName) {
  const ext = fileName?.split('.').pop()?.toLowerCase()
  if (ext === 'pdf')                        return { label: 'PDF',  className: 'type-pdf' }
  if (ext === 'docx' || ext === 'doc')      return { label: 'DOCX', className: 'type-docx' }
  if (ext === 'md' || ext === 'markdown')   return { label: '.MD',  className: 'type-md' }
  return { label: 'FILE', className: 'type-generic' }
}

function getDocumentIdFromIngestResponse(payload) {
  if (!payload || typeof payload !== 'object') return null
  const nested = payload.result && typeof payload.result === 'object' ? payload.result : null
  const candidates = [
    payload.doc_id, payload.document_id, payload.id,
    nested?.doc_id, nested?.document_id, nested?.id,
  ]
  return candidates.find((c) => typeof c === 'string' && c.trim()) || null
}

function getOrCreateUserId() {
  const existing = localStorage.getItem(STORAGE_KEYS.userId)
  if (existing) return existing
  const id = uuidv4()
  localStorage.setItem(STORAGE_KEYS.userId, id)
  return id
}

function parseErrorMessage(rawMessage) {
  if (!rawMessage) return 'Something went wrong. Please try again.'
  const trimmed = String(rawMessage).trim()
  if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
    try {
      const parsed = JSON.parse(trimmed)
      if (typeof parsed?.detail === 'string' && parsed.detail.trim()) return parsed.detail.trim()
    } catch { return trimmed }
  }
  return trimmed
}

function extractBestError(error) {
  const upstream = error?.payload?.upstream_detail
  if (upstream) {
    try {
      const parsed = JSON.parse(upstream)
      if (typeof parsed?.detail === 'string' && parsed.detail.trim()) return parsed.detail.trim()
    } catch {}
    if (typeof upstream === 'string' && upstream.trim()) return upstream.trim()
  }
  return parseErrorMessage(error?.message)
}

function waitForNextFrame() {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()))
}

export default function App() {
  const [userId]        = useState(() => getOrCreateUserId())
  const [apiKey, setApiKey]               = useState(() => localStorage.getItem(STORAGE_KEYS.apiKey) || '')
  const [selectedModel, setSelectedModel] = useState(() => localStorage.getItem(STORAGE_KEYS.selectedModel) || '')
  const [provider, setProvider]           = useState(() => localStorage.getItem(STORAGE_KEYS.provider) || '')

  const [chat, setChat]         = useState([])
  const [documents, setDocuments] = useState([])
  const [loadingState, setLoadingState] = useState('idle')
  const [loadingTask, setLoadingTask]   = useState('query')
  const [inlineFeedback, setInlineFeedback] = useState(null)
  const [documentPendingDeletion, setDocumentPendingDeletion] = useState(null)
  const [isDeletingDocument, setIsDeletingDocument] = useState(false)

  const stageTimerRef = useRef(null)

  const byokValidationMessage = getByokValidationMessage(apiKey, selectedModel, provider)
  const isByokReady = !byokValidationMessage
  const inputLocked = loadingState !== 'idle'

  useEffect(() => { localStorage.setItem(STORAGE_KEYS.apiKey, apiKey) }, [apiKey])
  useEffect(() => { localStorage.setItem(STORAGE_KEYS.selectedModel, selectedModel) }, [selectedModel])
  useEffect(() => { localStorage.setItem(STORAGE_KEYS.provider, provider) }, [provider])

  // Load persisted documents from backend on mount
  useEffect(() => {
    getDocuments(userId)
      .then((data) => {
        const docs = (data?.documents || []).map((d) => ({
          id: uuidv4(),
          doc_id: d.doc_id,
          name: d.filename || d.doc_id,
          status: 'uploaded',
          ...getDocumentTypeMeta(d.filename || ''),
        }))
        if (docs.length > 0) setDocuments(docs)
      })
      .catch(() => {}) // silent — no docs loaded on error
  }, [userId])

  // ─── message helpers ────────────────────────────────────────────────────────

  const addMessage = (msg) => setChat((prev) => [...prev, msg])

  const updateMessage = (id, updater) =>
    setChat((prev) => prev.map((m) => (m.id === id ? updater(m) : m)))

  // ─── stage animation ────────────────────────────────────────────────────────

  function startStageProgress(timelineId, stageDefs, pace) {
    let idx = 0
    clearInterval(stageTimerRef.current)

    function advance() {
      if (idx >= stageDefs.length - 1) return
      idx++
      updateMessage(timelineId, (m) => ({
        ...m,
        stages: m.stages.map((s, i) => ({
          ...s,
          status: i < idx ? 'done' : i === idx ? 'active' : 'pending',
        })),
      }))
      stageTimerRef.current = setTimeout(advance, pace[idx] ?? 600)
    }

    stageTimerRef.current = setTimeout(advance, pace[0] ?? 400)
  }

  function completeStages(timelineId, completionData) {
    clearInterval(stageTimerRef.current)
    updateMessage(timelineId, (m) => ({
      ...m,
      stages: m.stages.map((s) => ({ ...s, status: 'done' })),
      result: completionData,
    }))
  }

  function failStages(timelineId, errorMsg) {
    clearInterval(stageTimerRef.current)
    updateMessage(timelineId, (m) => ({
      ...m,
      stages: m.stages.map((s) =>
        s.status === 'active' || s.status === 'pending' ? { ...s, status: 'error' } : s
      ),
      error: errorMsg,
    }))
  }

  // ─── handlers ───────────────────────────────────────────────────────────────

  const handleSend = async (text) => {
    if (!text.trim() || inputLocked) return
    if (!isByokReady) {
      setInlineFeedback({ tone: 'warning', content: byokValidationMessage })
      return
    }
    setInlineFeedback(null)
    addMessage({ id: uuidv4(), role: 'user', content: text })

    const timelineId = uuidv4()
    addMessage({
      id: timelineId,
      role: 'timeline',
      operation: 'query',
      query: text,
      stages: buildStages(QUERY_STAGES),
      result: null,
      error: null,
    })

    setLoadingTask('query')
    setLoadingState('retrieving')
    startStageProgress(timelineId, QUERY_STAGES, QUERY_PACE)

    try {
      const result = await query(text, userId, apiKey, selectedModel, provider)

      const meta = result?.meta || {}
      completeStages(timelineId, {
        retrieved: meta.retrieved_count ?? null,
        reranked: meta.reranked_count ?? null,
        retrieve_ms: meta.retrieve_ms ?? null,
        generate_ms: meta.generate_ms ?? null,
        source_count: Array.isArray(result?.sources) ? result.sources.length : 0,
      })

      const generationTimeMs = Number(result?.meta?.generate_ms)
      if (Number.isFinite(generationTimeMs) && generationTimeMs > 0) {
        setLoadingState('generating')
        await waitForNextFrame()
      }

      addMessage({
        id: uuidv4(),
        role: 'assistant',
        content: result?.answer || result?.response || result?.message || 'No response returned.',
        sources: Array.isArray(result?.sources) ? result.sources : [],
      })
    } catch (error) {
      failStages(timelineId, extractBestError(error))
    } finally {
      setLoadingState('idle')
      setLoadingTask('query')
    }
  }

  const handleUpload = async (file) => {
    if (!file || inputLocked) return
    if (!isByokReady) {
      setInlineFeedback({ tone: 'warning', content: byokValidationMessage })
      return
    }
    setInlineFeedback(null)

    const timelineId = uuidv4()
    addMessage({
      id: timelineId,
      role: 'timeline',
      operation: 'upload',
      filename: file.name,
      stages: buildStages(UPLOAD_STAGES),
      result: null,
      error: null,
    })

    setLoadingTask('upload')
    setLoadingState('retrieving')
    startStageProgress(timelineId, UPLOAD_STAGES, UPLOAD_PACE)

    try {
      const ingestResult = await ingest(file, userId, apiKey)
      const docId = getDocumentIdFromIngestResponse(ingestResult)
      if (!docId) throw new Error('Upload response missing document identifier.')

      completeStages(timelineId, {
        chunk_count: ingestResult?.chunk_count ?? null,
        doc_id: docId,
      })

      const typeMeta = getDocumentTypeMeta(file.name)
      setDocuments((prev) => [
        ...prev,
        { id: uuidv4(), doc_id: docId, name: file.name, status: 'uploaded', ...typeMeta },
      ])
    } catch (error) {
      failStages(timelineId, extractBestError(error))
    } finally {
      setLoadingState('idle')
      setLoadingTask('query')
    }
  }

  const handleReset = async () => {
    clearInterval(stageTimerRef.current)
    try { await deleteAllDocuments(userId, apiKey) } catch {}
    localStorage.clear()
    const newId = uuidv4()
    localStorage.setItem(STORAGE_KEYS.userId, newId)
    // Reload page — cleanest reset that clears all state
    window.location.reload()
  }

  const handleRequestRemoveDocument = (document) => {
    if (!document?.doc_id) {
      addMessage({ id: uuidv4(), role: 'system', tone: 'error', content: 'Failed to delete document. Please try again.' })
      return
    }
    setDocumentPendingDeletion(document)
  }

  const handleConfirmRemoveDocument = async () => {
    if (!documentPendingDeletion || isDeletingDocument || !documentPendingDeletion.doc_id) {
      setDocumentPendingDeletion(null)
      return
    }
    setIsDeletingDocument(true)
    try {
      await deleteDocument(userId, documentPendingDeletion.doc_id, apiKey)
      setDocuments((prev) => prev.filter((d) => d.id !== documentPendingDeletion.id))
      addMessage({ id: uuidv4(), role: 'system', tone: 'success', content: `Document removed: ${documentPendingDeletion.name}` })
    } catch {
      addMessage({ id: uuidv4(), role: 'system', tone: 'error', content: 'Failed to delete document. Please try again.' })
    } finally {
      setIsDeletingDocument(false)
      setDocumentPendingDeletion(null)
    }
  }

  return (
    <div className="app-page">
      <div className="app-shell">
        <Header
          apiKey={apiKey}
          model={selectedModel}
          provider={provider}
          byokValidationMessage={byokValidationMessage}
          onApiKeyChange={setApiKey}
          onModelChange={setSelectedModel}
          onProviderChange={setProvider}
          onReset={handleReset}
        />
        <ChatWindow messages={chat} loadingState={loadingState} loadingTask={loadingTask} />
        <InputBar
          onSend={handleSend}
          onUpload={handleUpload}
          isLocked={inputLocked}
          isSendDisabled={!isByokReady}
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

        <AppFooter />

        <InfoModal
          isOpen={Boolean(documentPendingDeletion)}
          onClose={() => { if (!isDeletingDocument) setDocumentPendingDeletion(null) }}
          title="Delete document"
          footer={
            <button type="button" className="button button-danger" onClick={handleConfirmRemoveDocument} disabled={isDeletingDocument}>
              {isDeletingDocument ? 'Deleting…' : 'Delete permanently'}
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
