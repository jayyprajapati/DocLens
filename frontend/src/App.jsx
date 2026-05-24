import { useEffect, useMemo, useRef, useState } from 'react'
import { v4 as uuidv4 } from 'uuid'
import { getUserId } from './services/auth'
import Header from './components/Header'
import ChatWindow from './components/ChatWindow'
import InputBar from './components/InputBar'
import InfoModal from './components/InfoModal'
import AppFooter from './components/AppFooter'
import ThreadSidebar from './components/ThreadSidebar'
import {
  deleteAllDocuments,
  deleteDocument,
  deleteResource,
  deleteThread,
  getDocuments,
  getThread,
  ingest,
  listResources,
  listThreads,
  renameThread,
  uploadResource,
  chat as sendChat,
} from './services/api'
import './App.css'

const STORAGE_KEYS = {
  userId: 'doclens_user_id',
  apiKey: 'doclens_api_key',
  selectedModel: 'doclens_selected_model',
  provider: 'doclens_provider',
  theme: 'doclens_theme',
  activeThreadId: 'doclens_active_thread_id',
  sidebarOpen: 'doclens_sidebar_open',
  threadSummaries: 'doclens_thread_summaries',
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
const DRAFT_THREAD_ID = '__doclens_new_chat__'
const TITLE_MAX_CHARS = 58

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

function cleanTitleText(value) {
  return String(value || '')
    .replace(/\.[a-z0-9]{2,8}$/i, '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/[?.!,:;]+$/g, '')
    .trim()
}

function compactTitle(value, maxChars = TITLE_MAX_CHARS) {
  const clean = cleanTitleText(value)
  if (!clean) return ''
  if (clean.length <= maxChars) return clean
  const words = clean.split(' ')
  let title = ''
  for (const word of words) {
    const next = title ? `${title} ${word}` : word
    if (next.length > maxChars - 1) break
    title = next
  }
  return title ? `${title}…` : `${clean.slice(0, maxChars - 1).trim()}…`
}

function getDocumentLabel(filename) {
  const clean = compactTitle(filename, 42)
  return clean || 'document'
}

function getLatestUploadedFilename(messages) {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i]
    if (message?.role === 'timeline' && message.operation === 'upload' && message.filename) {
      return message.filename
    }
  }
  return ''
}

function buildQueryTitle(query, docName = '') {
  const raw = cleanTitleText(query)
  if (!raw) return docName ? `Question on ${getDocumentLabel(docName)}` : 'New document chat'

  if (docName && /\b(this|the)\s+(doc(ument)?|file|pdf|report|text|content|paper)\b/i.test(raw)) {
    if (/\bsummari[sz]e|summary|overview|brief\b/i.test(raw)) {
      return compactTitle(`Summary of ${getDocumentLabel(docName)}`)
    }
    return compactTitle(`Question on ${getDocumentLabel(docName)}`)
  }

  const withoutPoliteLead = raw
    .replace(/^(please\s+)?(can|could|would)\s+you\s+/i, '')
    .replace(/^(please\s+)?(tell me about|give me|show me|find|list|explain)\s+/i, '')
  return compactTitle(withoutPoliteLead || raw)
}

function buildThreadTitle(query, { chat, documents, docIds } = {}) {
  const scopedDoc = Array.isArray(docIds) && docIds.length
    ? documents.find((doc) => docIds.includes(doc.doc_id))?.name
    : ''
  const latestUpload = getLatestUploadedFilename(chat || [])
  return buildQueryTitle(query, scopedDoc || latestUpload)
}

function getDraftThreadTitle() {
  return 'New Chat'
}

function getStoredThreadSummaries() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEYS.threadSummaries) || '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function getDocIdFromIngestResponse(payload) {
  if (!payload || typeof payload !== 'object') return null
  const nested = payload.result && typeof payload.result === 'object' ? payload.result : null
  const candidates = [payload.doc_id, payload.document_id, payload.id,
    nested?.doc_id, nested?.document_id, nested?.id]
  return candidates.find((c) => typeof c === 'string' && c.trim()) || null
}

function parseErrorMessage(raw) {
  if (!raw) return 'Something went wrong.'
  const s = String(raw).trim()
  if (s.startsWith('{')) {
    try { const p = JSON.parse(s); if (p?.detail) return p.detail } catch {
      // Fall through to the raw string when the upstream detail is not JSON.
    }
  }
  return s
}

function extractBestError(error) {
  const upstream = error?.payload?.upstream_detail
  if (upstream) {
    try { const p = JSON.parse(upstream); if (p?.detail) return p.detail } catch {
      // Fall through to the raw upstream detail.
    }
    if (typeof upstream === 'string' && upstream.trim()) return upstream.trim()
  }
  return parseErrorMessage(error?.message)
}

export default function App() {
  const [userId]   = useState(() => getUserId())
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

  const [resources, setResources]             = useState([])
  const [resourcesLoading, setResourcesLoading] = useState(false)

  const [activeThreadId, setActiveThreadId] = useState(
    () => localStorage.getItem(STORAGE_KEYS.activeThreadId) || null,
  )
  const [threads, setThreads] = useState(() => getStoredThreadSummaries())
  const [isSidebarOpen, setIsSidebarOpen] = useState(
    () => localStorage.getItem(STORAGE_KEYS.sidebarOpen) !== 'false',
  )
  const [threadPendingDeletion, setThreadPendingDeletion] = useState(null)

  const stageTimerRef = useRef(null)
  const threadCacheRef = useRef({})

  const byokValidationMessage = getByokValidationMessage(apiKey, selectedModel, provider)
  const isByokReady = !byokValidationMessage
  const inputLocked = loadingState !== 'idle'
  const sidebarThreads = useMemo(() => {
    if (activeThreadId) return threads
    const draftThread = {
      id: DRAFT_THREAD_ID,
      title: getDraftThreadTitle(),
      message_count: chat.filter((message) => message.role !== 'system').length,
      updated_at: null,
      isDraft: true,
    }
    return [draftThread, ...threads.filter((thread) => thread.id !== DRAFT_THREAD_ID)]
  }, [activeThreadId, chat, threads])
  const sidebarActiveThreadId = activeThreadId || DRAFT_THREAD_ID
  const canStartNewChat = Boolean(activeThreadId) && !inputLocked

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
  useEffect(() => { localStorage.setItem(STORAGE_KEYS.sidebarOpen, String(isSidebarOpen)) }, [isSidebarOpen])
  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.threadSummaries, JSON.stringify(threads))
  }, [threads])
  useEffect(() => {
    if (activeThreadId) localStorage.setItem(STORAGE_KEYS.activeThreadId, activeThreadId)
    else localStorage.removeItem(STORAGE_KEYS.activeThreadId)
  }, [activeThreadId])

  // Load persisted documents on mount
  useEffect(() => {
    getDocuments().then((data) => {
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

  // Load threads list on mount
  const refreshThreads = async () => {
    try {
      const data = await listThreads()
      const nextThreads = Array.isArray(data?.threads) ? data.threads : []
      setThreads((prev) => nextThreads.length > 0 || prev.length === 0 ? nextThreads : prev)
    } catch {
      setThreads((prev) => prev)
    }
  }

  useEffect(() => { refreshThreads() }, [userId])

  // Load workspace resources on mount
  const loadResources = async () => {
    try {
      const data = await listResources()
      setResources(data.documents || [])
    } catch {
      // non-fatal — sidebar will show empty state
    }
  }

  useEffect(() => { loadResources() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleResourceUpload = async (file) => {
    if (!file) return
    setResourcesLoading(true)
    try {
      await uploadResource(file)
      await loadResources()
    } catch {
      // leave loading false, silent failure
    } finally {
      setResourcesLoading(false)
    }
  }

  const handleResourceDelete = async (docId) => {
    try {
      await deleteResource(docId)
      setResources((prev) => prev.filter((d) => (d.id || d.doc_id) !== docId))
    } catch {
      // silent failure — list will still reflect the attempted removal
    }
  }

  // If we have a persisted activeThreadId, hydrate its messages on mount
  useEffect(() => {
    if (!activeThreadId) return
    let cancelled = false
    getThread(activeThreadId).then((data) => {
      if (cancelled || !data) return
      const loaded = (data.messages || []).map((m) => ({
        id: `msg-${m.id}`,
        role: m.role,
        content: m.content,
        sources: m.citations || [],
        skipTyping: true,
      }))
      setChat(loaded)
    }).catch(() => {
      // Thread gone — clear stale id
      setActiveThreadId(null)
      setChat([])
    })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Keep thread cache in sync so timeline timing survives thread switches
  useEffect(() => {
    if (activeThreadId && chat.length > 0) {
      threadCacheRef.current[activeThreadId] = chat
    }
  }, [chat, activeThreadId])

  // ─── message helpers ────────────────────────────────────────────
  const addMessage = (msg) => setChat((prev) => [...prev, msg])
  const updateMessage = (id, fn) => setChat((prev) => prev.map((m) => m.id === id ? fn(m) : m))
  const upsertThreadSummary = (threadId, title) => {
    if (!threadId) return
    const now = Math.floor(Date.now() / 1000)
    setThreads((prev) => {
      const existing = prev.find((thread) => thread.id === threadId)
      const next = {
        ...existing,
        id: threadId,
        title: title || existing?.title || 'New document chat',
        updated_at: now,
        message_count: Math.max(existing?.message_count || 0, 2),
      }
      return [next, ...prev.filter((thread) => thread.id !== threadId)]
    })
  }

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
  async function runChatTurn(text, { docIds } = {}) {
    const timelineId = uuidv4()
    addMessage({
      id: timelineId,
      role: 'timeline',
      operation: 'query',
      query: docIds ? `${text} [scoped]` : text,
      stages: buildStages(QUERY_STAGES),
      result: null,
      error: null,
    })

    setLoadingState('retrieving')
    startStageProgress(timelineId, QUERY_STAGES, QUERY_PACE)

    try {
      const wasNewThread = !activeThreadId
      const result = await sendChat({
        query: text,
        apiKey,
        model: selectedModel,
        provider,
        threadId: activeThreadId,
        docIds,
      })

      const generatedTitle = buildThreadTitle(text, { chat, documents, docIds })

      // Pick up new thread id if Cortex just created one
      if (result?.thread_id && result.thread_id !== activeThreadId) {
        upsertThreadSummary(result.thread_id, generatedTitle)
        setActiveThreadId(result.thread_id)
      }

      const meta = result?.meta || {}
      const answer = typeof result?.answer === 'string'
        ? result.answer
        : (result?.answer && JSON.stringify(result.answer)) || 'No response returned.'
      const sources = Array.isArray(result?.citations) && result.citations.length
        ? result.citations
        : (Array.isArray(result?.sources) ? result.sources : [])

      completeStages(timelineId, {
        retrieved: meta.retrieved_count ?? null,
        reranked: meta.reranked_count ?? null,
        retrieve_ms: meta.retrieve_ms ?? meta.retrieval_time ?? null,
        generate_ms: meta.generate_ms ?? meta.generation_time ?? null,
        grounded: result?.grounded ?? null,
        streaming: false,
      })

      addMessage({
        id: uuidv4(),
        role: 'assistant',
        content: answer,
        sources,
      })

      if (wasNewThread && result?.thread_id) {
        if (generatedTitle.length >= 3) {
          try {
            await renameThread(result.thread_id, generatedTitle)
          } catch {
            // Keep the answered turn intact even if Cortex rejects a title patch.
          } finally {
            await refreshThreads()
          }
        } else {
          await refreshThreads()
        }
      } else {
        await refreshThreads()
      }
    } catch (error) {
      failStages(timelineId, extractBestError(error))
    } finally {
      setLoadingState('idle')
    }
  }

  const handleSend = async (text) => {
    if (!text.trim() || inputLocked) return
    if (!isByokReady) {
      setInlineFeedback({ tone: 'warning', content: byokValidationMessage })
      return
    }
    setInlineFeedback(null)
    addMessage({ id: uuidv4(), role: 'user', content: text })

    // Multi-doc clarification — only fires on a fresh thread (no thread_id yet).
    // Once a thread is established, its doc_ids are fixed server-side.
    if (!activeThreadId && documents.length > 1 && AMBIGUOUS_DOC_RE.test(text)) {
      addMessage({
        id: uuidv4(),
        role: 'doc-select',
        query: text,
        documents: documents.map((d) => ({ id: d.id, doc_id: d.doc_id, name: d.name, typeLabel: d.typeLabel, typeClassName: d.typeClassName })),
      })
      return
    }

    await runChatTurn(text)
  }

  // Called when user picks a document in the doc-select message
  const handleDocSelect = async (docId, _docName, originalQuery) => {
    await runChatTurn(originalQuery, { docIds: [docId] })
  }

  const handleNewChat = () => {
    if (!canStartNewChat) return
    setActiveThreadId(null)
    setChat([])
    setInlineFeedback(null)
  }

  const handleSelectThread = async (threadId) => {
    if (threadId === DRAFT_THREAD_ID) {
      if (activeThreadId) {
        setActiveThreadId(null)
        setChat([])
        setInlineFeedback(null)
      }
      return
    }
    if (threadId === activeThreadId) return
    // Restore from in-memory cache to preserve timeline timing data
    if (threadCacheRef.current[threadId]) {
      setChat(threadCacheRef.current[threadId])
      setActiveThreadId(threadId)
      return
    }
    try {
      const data = await getThread(threadId)
      const loaded = (data?.messages || []).map((m) => ({
        id: `msg-${m.id}`,
        role: m.role,
        content: m.content,
        sources: m.citations || [],
        skipTyping: true,
      }))
      setChat(loaded)
      setActiveThreadId(threadId)
    } catch {
      setInlineFeedback({ tone: 'error', content: 'Could not load chat history.' })
    }
  }

  const handleDeleteThread = (threadId) => {
    setThreadPendingDeletion(threadId)
  }

  const confirmDeleteThread = async () => {
    if (!threadPendingDeletion) return
    const tid = threadPendingDeletion
    setThreadPendingDeletion(null)
    try {
      await deleteThread(tid)
      setThreads((prev) => prev.filter((thread) => thread.id !== tid))
      if (tid === activeThreadId) {
        setActiveThreadId(null)
        setChat([])
      }
      refreshThreads()
    } catch {
      setInlineFeedback({ tone: 'error', content: 'Could not delete chat.' })
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
      const ingestResult = await ingest(file, apiKey, activeThreadId)
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
    try { await deleteAllDocuments(apiKey) } catch {
      // Reset should still clear the local session if upstream cleanup is unavailable.
    }
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
      await deleteDocument(documentPendingDeletion.doc_id, apiKey)
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
        <ThreadSidebar
          threads={sidebarThreads}
          activeThreadId={sidebarActiveThreadId}
          onSelect={handleSelectThread}
          onNewChat={handleNewChat}
          canStartNewChat={canStartNewChat}
          onDelete={handleDeleteThread}
          isOpen={isSidebarOpen}
          onClose={() => setIsSidebarOpen(false)}
          theme={theme}
          onThemeChange={setTheme}
          userId={userId}
          apiKey={apiKey}
          model={selectedModel}
          provider={provider}
          byokValidationMessage={byokValidationMessage}
          onApiKeyChange={setApiKey}
          onModelChange={setSelectedModel}
          onProviderChange={setProvider}
          onReset={handleReset}
          resources={resources}
          resourcesLoading={resourcesLoading}
          onResourceUpload={handleResourceUpload}
          onResourceDelete={handleResourceDelete}
        />
        <div className="app-shell-main">
        <Header
          apiKey={apiKey} model={selectedModel} provider={provider}
          byokValidationMessage={byokValidationMessage}
          onApiKeyChange={setApiKey} onModelChange={setSelectedModel}
          onProviderChange={setProvider} onReset={handleReset}
          isSidebarOpen={isSidebarOpen}
          onSidebarToggle={() => setIsSidebarOpen((v) => !v)}
        />
        <ChatWindow
          messages={chat}
          onDocSelect={handleDocSelect}
          documents={documents}
        />
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
        <InfoModal
          isOpen={Boolean(threadPendingDeletion)}
          onClose={() => setThreadPendingDeletion(null)}
          title="Delete chat"
          footer={
            <button type="button" className="button button-danger" onClick={confirmDeleteThread}>
              Delete permanently
            </button>
          }
        >
          <p>This will permanently delete this conversation and all its messages.</p>
        </InfoModal>
        </div>
      </div>
    </div>
  )
}
