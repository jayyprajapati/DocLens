// DocLens/frontend/src/services/api.js

import { getAuthHeaders } from './auth'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')

async function parseResponse(response) {
  const contentType = response.headers.get('content-type') || ''
  const isJson = contentType.includes('application/json')
  const payload = isJson ? await response.json() : await response.text()

  if (!response.ok) {
    const message =
      (isJson && payload?.detail) ||
      (typeof payload === 'string' && payload) ||
      `Request failed with status ${response.status}`

    const error = new Error(message)
    error.status = response.status

    if (isJson && payload && typeof payload === 'object') {
      error.code = payload.error || null
      error.usage = payload.usage || null
      error.payload = payload
    }

    throw error
  }

  return payload
}

// Retry-with-backoff for rate-limited write endpoints (HTTP 429).
async function withBackoff(fn, maxRetries = 2) {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn()
    } catch (err) {
      if (err.status !== 429 || attempt === maxRetries) throw err
      await new Promise(r => setTimeout(r, 5000 * (attempt + 1)))
    }
  }
}

export async function query(query, apiKey, model, provider, docIds) {
  const body = { query }
  if (apiKey?.trim()) body.api_key = apiKey.trim()
  if (model?.trim()) body.model = model.trim()
  if (provider?.trim()) body.provider = provider.trim()
  if (Array.isArray(docIds) && docIds.length) body.doc_ids = docIds

  return withBackoff(() =>
    fetch(`${API_BASE_URL}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(body),
    }).then(parseResponse)
  )
}

export async function chat({ query, apiKey, model, provider, threadId, docIds }) {
  const body = { query }
  if (apiKey?.trim()) body.api_key = apiKey.trim()
  if (model?.trim()) body.model = model.trim()
  if (provider?.trim()) body.provider = provider.trim()
  if (threadId) body.thread_id = threadId
  if (Array.isArray(docIds) && docIds.length) body.doc_ids = docIds

  const response = await fetch(`${API_BASE_URL}/chat?stream=false`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(body),
  })
  return parseResponse(response)
}

function parseSseBlock(block) {
  let event = 'message'
  const dataLines = []
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
  }
  const rawData = dataLines.join('\n')
  let data = rawData
  if (rawData) {
    try { data = JSON.parse(rawData) } catch { /* pass text through */ }
  }
  return { event, data }
}

// POST /chat/stream proxies Cortex SSE and appends thread metadata.
// thread_id may arrive in `done` or a separate `thread` event depending on backend version.
export async function streamChat({ query, apiKey, model, provider, threadId, docIds, onEvent }) {
  const body = { query }
  if (apiKey?.trim()) body.api_key = apiKey.trim()
  if (model?.trim()) body.model = model.trim()
  if (provider?.trim()) body.provider = provider.trim()
  if (threadId) body.thread_id = threadId
  if (Array.isArray(docIds) && docIds.length) body.doc_ids = docIds

  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...getAuthHeaders(),
    },
    body: JSON.stringify(body),
  })

  if (!response.ok) return parseResponse(response)
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    const payload = await response.json()
    const summary = {
      answer: typeof payload?.answer === 'string'
        ? payload.answer
        : (payload?.answer && JSON.stringify(payload.answer)) || '',
      citations: Array.isArray(payload?.citations)
        ? payload.citations
        : (Array.isArray(payload?.sources) ? payload.sources : []),
      meta: payload?.meta || {},
      grounded: payload?.grounded ?? null,
      thread_id: payload?.thread_id || threadId || null,
    }
    onEvent?.({ event: 'done', data: payload }, { ...summary })
    return summary
  }
  if (!response.body) throw new Error('Streaming is not supported by this browser.')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  const summary = {
    answer: '',
    citations: [],
    meta: {},
    grounded: null,
    thread_id: threadId || null,
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })

    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() || ''

    for (const block of blocks) {
      if (!block.trim()) continue
      const parsed = parseSseBlock(block)
      const { event, data } = parsed

      if (event === 'delta' || event === 'clarification') {
        const text = typeof data?.text === 'string' ? data.text : ''
        summary.answer += text
      } else if (event === 'citations') {
        summary.citations = Array.isArray(data?.citations) ? data.citations : []
      } else if (event === 'meta') {
        summary.meta = { ...summary.meta, ...(data && typeof data === 'object' ? data : {}) }
      } else if (event === 'done') {
        summary.meta = { ...summary.meta, ...(data && typeof data === 'object' ? data : {}) }
        if (typeof data?.answer === 'string' && !summary.answer) summary.answer = data.answer
        if (typeof data?.content === 'string' && !summary.answer) summary.answer = data.content
        if (Array.isArray(data?.citations) && data.citations.length) summary.citations = data.citations
        if (Array.isArray(data?.sources) && data.sources.length) summary.citations = data.sources
        if (typeof data?.grounded === 'boolean') summary.grounded = data.grounded
        // thread_id now arrives in done (not a separate thread event)
        if (data?.thread_id) summary.thread_id = data.thread_id
      } else if (event === 'thread') {
        // kept for backward compat during rollout
        summary.thread_id = data?.thread_id || summary.thread_id
      } else if (event === 'error') {
        throw new Error(data?.message || 'Streaming response failed.')
      }

      onEvent?.(parsed, { ...summary })
    }

    if (done) break
  }

  if (buffer.trim()) {
    const parsed = parseSseBlock(buffer)
    onEvent?.(parsed, { ...summary })
  }

  return summary
}

// Thread endpoints — user identity comes from JWT, no user_id query param needed.
export async function listThreads() {
  const response = await fetch(`${API_BASE_URL}/threads`, { headers: getAuthHeaders() })
  return parseResponse(response)
}

export async function getThread(threadId) {
  const response = await fetch(`${API_BASE_URL}/threads/${threadId}`, { headers: getAuthHeaders() })
  return parseResponse(response)
}

export async function deleteThread(threadId) {
  const response = await fetch(`${API_BASE_URL}/threads/${threadId}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  })
  return parseResponse(response)
}

export async function renameThread(threadId, title) {
  const response = await fetch(`${API_BASE_URL}/threads/${threadId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ title }),
  })
  return parseResponse(response)
}

export async function ingest(file, apiKey, threadId) {
  const formData = new FormData()
  formData.append('file', file)
  if (apiKey?.trim()) formData.append('api_key', apiKey.trim())
  if (threadId) formData.append('thread_id', threadId)

  return withBackoff(() =>
    fetch(`${API_BASE_URL}/ingest`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: formData,
    }).then(parseResponse)
  )
}

export async function generate(prompt) {
  return withBackoff(() =>
    fetch(`${API_BASE_URL}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ prompt }),
    }).then(parseResponse)
  )
}

export async function deleteDocument(docId, apiKey) {
  const body = { doc_id: docId }
  if (apiKey?.trim()) body.api_key = apiKey.trim()

  const response = await fetch(`${API_BASE_URL}/delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(body),
  })
  return parseResponse(response)
}

export async function getDocuments() {
  const response = await fetch(`${API_BASE_URL}/documents`, { headers: getAuthHeaders() })
  return parseResponse(response)
}

export async function fetchModels(provider, apiKey) {
  const params = new URLSearchParams({ provider })
  if (apiKey?.trim()) params.append('api_key', apiKey.trim())
  const response = await fetch(`${API_BASE_URL}/models?${params}`, { headers: getAuthHeaders() })
  return parseResponse(response)
}

export async function deleteAllDocuments(apiKey) {
  const body = {}
  if (apiKey?.trim()) body.api_key = apiKey.trim()

  const response = await fetch(`${API_BASE_URL}/delete_all`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(body),
  })
  return parseResponse(response)
}

export async function listResources() {
  const response = await fetch(`${API_BASE_URL}/resources`, { headers: getAuthHeaders() })
  return parseResponse(response)
}

export async function uploadResource(file) {
  const formData = new FormData()
  formData.append('file', file)
  const response = await fetch(`${API_BASE_URL}/resources`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: formData,
  })
  return parseResponse(response)
}

export async function deleteResource(docId) {
  const response = await fetch(`${API_BASE_URL}/resources/${docId}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  })
  return parseResponse(response)
}
