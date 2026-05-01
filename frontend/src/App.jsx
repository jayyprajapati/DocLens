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
  theme: 'doclens_theme',
}

const UPLOAD_STAGES = [
  { id: 'receiving',  label: 'Receiving file' },
  { id: 'parsing',    label: 'Parsing document' },
  { id: 'embedding',  label: 'Generating embeddings' },
  { id: 'storing',    label: 'Storing vectors' },
]

const QUERY_STAGES = [
  { id: 'embedding',  label: 'Embedding query' },
  { id: 'searching',  label: 'Searching documents' },
  { id: 'reranking',  label: 'Re-ranking results' },
  { id: 'generating', label: 'Generating answer' },
]

const UPLOAD_PACE = [300, 900, 1600, 700]
const QUERY_PACE  = [250, 550, 450, 350]

// Detects if a query ambiguously references a single document
const AMBIGUOUS_DOC_RE = /\b(this|the)\s+(doc(ument)?|file|pdf|report|text|content|paper)\b/i

function buildStages(defs) {
  return defs.map((s, i) => ({
    ...s,
    status: i === 0 ? 'active' : 'pending',
    elapsedMs: null,
    startedAt: i === 0 ? Date.now() : null,
  }))
}

function getByokValidationMessage(apiKey, model, provider) {
  const ok = [Boolean(apiKey.trim()), Boolean(model.trim()), Boolean(provider.trim())]
  if (ok.every(Boolean)) return ''
  const missing = []
  if (!ok[2]) missing.push('provider')
  if (!ok[0]) missing.push('API key')
  if (!ok[1]) missing.push('model')
  if (missing.length === 3) return 'Select a provider, add your API key, and choose a model.'
  return `Add your ${missing.join(' and ')} to continue.`
}

function getDocumentTypeMeta(fileName) {
  const ext = (fileName || '').split('.').pop().toLowerCase()
  if (ext === 'pdf')  return { typeLabel: 'PDF',  typeClassName: 'type-pdf' }
  if (ext === 'docx' || ext === 'doc') return { typeLabel: 'DOCX', typeClassName: 'type-docx' }
  if (ext === 'md' || ext === 'markdown') return { typeLabel: 'MD', typeClassName: 'type-md' }
  return { typeLabel: 'FILE', typeClassName: 'type-generic' }
}

function getDocIdFromIngestResponse(payload) {
  if (!payload || typeof payload !== 'object') return null
  const nested = payload.result && typeof payload.result === 'object' ? payload.result : null
  const candidates = [payload.doc_id, payload.document_id, payload.id,
    nested?.doc_id, nested?.document_id, nested?.id]
  return candidates.find((c) => typeof c === 'string' && c.trim()) || null
}

function getOrCreateUserId() {
  const existing = localStorage.getItem(STORAGE_KEYS.userId)
  if (existing) return existing
  const id = uuidv4()
  localStorage.setItem(STORAGE_KEYS.userId, id)
  return id
}

function parseErrorMessage(raw) {
  if (!raw) return 'Something went wrong.'
  const s = String(raw).trim()
  if (s.startsWith('{')) {
    try { const p = JSON.parse(s); if (p?.detail) return p.detail } catch {}
  }
  return s
}

function extractBestError(error) {
  const upstream = error?.payload?.upstream_detail
  if (upstream) {
    try { const p = JSON.parse(upstream); if (p?.detail) return p.detail } catch {}
    if (typeof upstream === 'string' && upstream.trim()) return upstream.trim()
  }
  return parseErrorMessage(error?.message)
}

export default function App() {
  const [userId]   = useState(() => getOrCreateUserId())
  const [apiKey, setApiKey]           = useState(() => localStorage.getItem(STORAGE_KEYS.apiKey) || '')
  const [selectedModel, setSelectedModel] = useState(() => localStorage.getItem(STORAGE_KEYS.selectedModel) || '')
  const [provider, setProvider]       = useState(() => localStorage.getItem(STORAGE_KEYS.provider) || '')
  const [theme, setTheme]             = useState(() => localStorage.getItem(STORAGE_KEYS.theme) || 'light')

  const [chat, setChat]               = useState([])
  const [documents, setDocuments]     = useState([])
  const [loadingState, setLoadingState] = useState('idle')
  const [inlineFeedback, setInlineFeedback] = useState(null)
  const [documentPendingDeletion, setDocumentPendingDeletion] = useState(null)
  const [isDeletingDocument, setIsDeletingDocument] = useState(false)

  const stageTimerRef = useRef(null)

  const byokValidationMessage = getByokValidationMessage(apiKey, selectedModel, provider)
  const isByokReady = !byokValidationMessage
  const inputLocked = loadingState !== 'idle'

  // Apply theme class to root
  useEffect(() => {
    const root = document.documentElement
    root.classList.remove('theme-light', 'theme-dark')
    if (theme === 'light') root.classList.add('theme-light')
    else if (theme === 'dark') root.classList.add('theme-dark')
  }, [theme])

  useEffect(() => { localStorage.setItem(STORAGE_KEYS.apiKey, apiKey) }, [apiKey])
  useEffect(() => { localStorage.setItem(STORAGE_KEYS.selectedModel, selectedModel) }, [selectedModel])
  useEffect(() => { localStorage.setItem(STORAGE_KEYS.provider, provider) }, [provider])
  useEffect(() => { localStorage.setItem(STORAGE_KEYS.theme, theme) }, [theme])

  // Load persisted documents on mount
  useEffect(() => {
    getDocuments(userId).then((data) => {
      const docs = (data?.documents || []).map((d) => ({
        id: uuidv4(),
        doc_id: d.doc_id,
        name: d.filename || `doc-${d.doc_id.slice(0, 8)}`,
        status: 'uploaded',
        ...getDocumentTypeMeta(d.filename || ''),
      }))
      if (docs.length) setDocuments(docs)
    }).catch(() => {})
  }, [userId])

  // ─── message helpers ────────────────────────────────────────────
  const addMessage = (msg) => setChat((prev) => [...prev, msg])
  const updateMessage = (id, fn) => setChat((prev) => prev.map((m) => m.id === id ? fn(m) : m))

  // ─── stage animation with per-stage timing ──────────────────────
  function startStageProgress(timelineId, stageDefs, pace) {
    let idx = 0
    clearTimeout(stageTimerRef.current)

    function advance() {
      if (idx >= stageDefs.length - 1) return
      const prevIdx = idx
      idx++
      const now = Date.now()
      updateMessage(timelineId, (m) => ({
        ...m,
        stages: m.stages.map((s, i) => {
          if (i < prevIdx) return s
          if (i === prevIdx) return { ...s, status: 'done', elapsedMs: now - (s.startedAt || now) }
          if (i === idx)     return { ...s, status: 'active', startedAt: now }
          return s
        }),
      }))
      stageTimerRef.current = setTimeout(advance, pace[idx] ?? 600)
    }

    stageTimerRef.current = setTimeout(advance, pace[0] ?? 400)
  }

  function completeStages(timelineId, completionData) {
    clearTimeout(stageTimerRef.current)
    const now = Date.now()
    updateMessage(timelineId, (m) => ({
      ...m,
      stages: m.stages.map((s) => ({
        ...s,
        status: 'done',
        elapsedMs: s.elapsedMs ?? (s.startedAt ? now - s.startedAt : null),
      })),
      result: completionData,
    }))
  }

  function failStages(timelineId, errorMsg) {
    clearTimeout(stageTimerRef.current)
    updateMessage(timelineId, (m) => ({
      ...m,
      stages: m.stages.map((s) =>
        s.status === 'active' ? { ...s, status: 'error' } : s.status === 'pending' ? { ...s, status: 'pending' } : s
      ),
      error: errorMsg,
    }))
  }

  // ─── handlers ───────────────────────────────────────────────────
  const handleSend = async (text) => {
    if (!text.trim() || inputLocked) return
    if (!isByokReady) {
      setInlineFeedback({ tone: 'warning', content: byokValidationMessage })
      return
    }
    setInlineFeedback(null)
    addMessage({ id: uuidv4(), role: 'user', content: text })

    // Multi-doc clarification: if user has multiple docs and query is ambiguous
    if (documents.length > 1 && AMBIGUOUS_DOC_RE.test(text)) {
      addMessage({
        id: uuidv4(),
        role: 'doc-select',
        query: text,
        documents: documents.map((d) => ({ id: d.id, doc_id: d.doc_id, name: d.name, typeLabel: d.typeLabel, typeClassName: d.typeClassName })),
      })
      return
    }

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
        answer: result?.answer || result?.response || 'No response returned.',
        sources: Array.isArray(result?.sources) ? result.sources : [],
      })
    } catch (error) {
      failStages(timelineId, extractBestError(error))
    } finally {
      setLoadingState('idle')
    }
  }

  // Called when user picks a document in the doc-select message
  const handleDocSelect = async (docId, docName, originalQuery) => {
    const timelineId = uuidv4()
    addMessage({
      id: timelineId,
      role: 'timeline',
      operation: 'query',
      query: `${originalQuery} [in ${docName}]`,
      stages: buildStages(QUERY_STAGES),
      result: null,
      error: null,
    })

    setLoadingState('retrieving')
    startStageProgress(timelineId, QUERY_STAGES, QUERY_PACE)

    try {
      const result = await query(originalQuery, userId, apiKey, selectedModel, provider, [docId])
      const meta = result?.meta || {}
      completeStages(timelineId, {
        retrieved: meta.retrieved_count ?? null,
        reranked: meta.reranked_count ?? null,
        retrieve_ms: meta.retrieve_ms ?? null,
        generate_ms: meta.generate_ms ?? null,
        answer: result?.answer || result?.response || 'No response returned.',
        sources: Array.isArray(result?.sources) ? result.sources : [],
      })
    } catch (error) {
      failStages(timelineId, extractBestError(error))
    } finally {
      setLoadingState('idle')
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

    setLoadingState('retrieving')
    startStageProgress(timelineId, UPLOAD_STAGES, UPLOAD_PACE)

    try {
      const ingestResult = await ingest(file, userId, apiKey)
      const docId = getDocIdFromIngestResponse(ingestResult)
      if (!docId) throw new Error('Upload response missing document identifier.')

      completeStages(timelineId, {
        chunk_count: ingestResult?.chunk_count ?? null,
        doc_id: docId,
      })

      const typeMeta = getDocumentTypeMeta(file.name)
      setDocuments((prev) => [...prev, { id: uuidv4(), doc_id: docId, name: file.name, status: 'uploaded', ...typeMeta }])
    } catch (error) {
      failStages(timelineId, extractBestError(error))
    } finally {
      setLoadingState('idle')
    }
  }

  const handleReset = async () => {
    clearTimeout(stageTimerRef.current)
    try { await deleteAllDocuments(userId, apiKey) } catch {}
    localStorage.clear()
    window.location.reload()
  }

  const handleRequestRemoveDocument = (document) => {
    if (!document?.doc_id) return
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
      addMessage({ id: uuidv4(), role: 'system', tone: 'success', content: `Removed: ${documentPendingDeletion.name}` })
    } catch {
      addMessage({ id: uuidv4(), role: 'system', tone: 'error', content: 'Failed to remove document.' })
    } finally {
      setIsDeletingDocument(false)
      setDocumentPendingDeletion(null)
    }
  }

  return (
    <div className="app-page">
      <div className="app-shell">
        <Header
          apiKey={apiKey} model={selectedModel} provider={provider} theme={theme}
          byokValidationMessage={byokValidationMessage}
          onApiKeyChange={setApiKey} onModelChange={setSelectedModel}
          onProviderChange={setProvider} onThemeChange={setTheme} onReset={handleReset}
          userId={userId}
        />
        <ChatWindow messages={chat} onDocSelect={handleDocSelect} />
        <InputBar
          onSend={handleSend} onUpload={handleUpload}
          isLocked={inputLocked} isSendDisabled={!isByokReady}
          documents={documents} onRequestRemoveDocument={handleRequestRemoveDocument}
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
          title="Remove document"
          footer={
            <button type="button" className="button button-danger" onClick={handleConfirmRemoveDocument} disabled={isDeletingDocument}>
              {isDeletingDocument ? 'Removing…' : 'Remove permanently'}
            </button>
          }
        >
          <p>This will permanently delete this document from the index.</p>
          {documentPendingDeletion?.name && <p><strong>{documentPendingDeletion.name}</strong></p>}
        </InfoModal>
      </div>
    </div>
  )
}
