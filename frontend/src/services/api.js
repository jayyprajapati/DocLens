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

export async function chat({ query, apiKey, model, provider, threadId, docIds }) {
  const body = { query }
  if (apiKey?.trim()) body.api_key = apiKey.trim()
  if (model?.trim()) body.model = model.trim()
  if (provider?.trim()) body.provider = provider.trim()
  if (threadId) body.thread_id = threadId
  if (Array.isArray(docIds) && docIds.length) body.doc_ids = docIds

  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(body),
  })
  return parseResponse(response)
}

// Thread endpoints — user identity comes from the bearer token, no user_id query param needed.
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

// Per-chat attachments for a given thread. A draft (no thread yet) has none.
export async function getDocuments(threadId) {
  if (!threadId) return { documents: [] }
  const params = new URLSearchParams({ thread_id: threadId })
  const response = await fetch(`${API_BASE_URL}/documents?${params}`, { headers: getAuthHeaders() })
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
