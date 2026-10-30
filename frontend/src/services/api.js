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

// Authenticated fetch: attaches the session token and, if the server no longer accepts it
// (expired / secret rotated), mints a fresh session once and retries.
async function authed(path, init = {}) {
  const send = async (force) => fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { ...(init.headers || {}), ...(await getAuthHeaders(force)) },
  })
  let response = await send(false)
  if (response.status === 401) response = await send(true)
  return parseResponse(response)
}

// Retry-with-backoff for rate-limited write endpoints (HTTP 429). Quota errors are final.
async function withBackoff(fn, maxRetries = 2) {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn()
    } catch (err) {
      if (err.status !== 429 || err.code !== 'rate_limited' || attempt === maxRetries) throw err
      await new Promise(r => setTimeout(r, 5000 * (attempt + 1)))
    }
  }
}

const jsonInit = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export async function fetchPublicConfig() {
  return authed('/config')
}

export async function chat({ query, apiKey, model, provider, threadId, docIds }) {
  const body = { query }
  if (provider?.trim()) body.provider = provider.trim()
  if (provider !== 'hosted') {
    if (apiKey?.trim()) body.api_key = apiKey.trim()
    if (model?.trim()) body.model = model.trim()
  }
  if (threadId) body.thread_id = threadId
  if (Array.isArray(docIds) && docIds.length) body.doc_ids = docIds
  return authed('/chat', jsonInit('POST', body))
}

// Thread endpoints — user identity comes from the session token.
export async function listThreads() {
  return authed('/threads')
}

export async function getThread(threadId) {
  return authed(`/threads/${encodeURIComponent(threadId)}`)
}

export async function deleteThread(threadId) {
  return authed(`/threads/${encodeURIComponent(threadId)}`, { method: 'DELETE' })
}

export async function renameThread(threadId, title) {
  return authed(`/threads/${encodeURIComponent(threadId)}`, jsonInit('PATCH', { title }))
}

export async function ingest(file, _apiKey, threadId) {
  const formData = new FormData()
  formData.append('file', file)
  if (threadId) formData.append('thread_id', threadId)
  return withBackoff(() => authed('/ingest', { method: 'POST', body: formData }))
}

export async function deleteDocument(docId) {
  return authed('/delete', jsonInit('POST', { doc_id: docId }))
}

// Per-chat attachments for a given thread. A draft (no thread yet) has none.
export async function getDocuments(threadId) {
  if (!threadId) return { documents: [] }
  return authed(`/documents?${new URLSearchParams({ thread_id: threadId })}`)
}

export async function fetchModels(provider, apiKey) {
  // The key goes in a header, never the URL (URLs are logged by proxies and servers).
  const headers = {}
  if (apiKey?.trim()) headers['X-Provider-Key'] = apiKey.trim()
  return authed(`/models?${new URLSearchParams({ provider })}`, { headers })
}

export async function deleteAllDocuments() {
  return authed('/delete_all', jsonInit('POST', {}))
}

export async function listResources() {
  return authed('/resources')
}

export async function uploadResource(file) {
  const formData = new FormData()
  formData.append('file', file)
  return withBackoff(() => authed('/resources', { method: 'POST', body: formData }))
}

export async function deleteResource(docId) {
  return authed(`/resources/${encodeURIComponent(docId)}`, { method: 'DELETE' })
}
