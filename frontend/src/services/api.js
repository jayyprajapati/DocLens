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

export async function query(query, userId, apiKey, model, provider, docIds) {
  const body = {
    query,
    user_id: userId,
  }

  if (apiKey?.trim()) {
    body.api_key = apiKey.trim()
  }

  if (model?.trim()) {
    body.model = model.trim()
  }

  if (provider?.trim()) {
    body.provider = provider.trim()
  }

  if (Array.isArray(docIds) && docIds.length) {
    body.doc_ids = docIds
  }

  const response = await fetch(`${API_BASE_URL}/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })

  return parseResponse(response)
}

export async function chat({ query, userId, apiKey, model, provider, threadId, docIds }) {
  const body = {
    query,
    user_id: userId,
  }

  if (apiKey?.trim()) body.api_key = apiKey.trim()
  if (model?.trim()) body.model = model.trim()
  if (provider?.trim()) body.provider = provider.trim()
  if (threadId) body.thread_id = threadId
  if (Array.isArray(docIds) && docIds.length) body.doc_ids = docIds

  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
    try { data = JSON.parse(rawData) } catch {
      // Non-JSON SSE data is passed through as text.
    }
  }
  return { event, data }
}

export async function streamChat({ query, userId, apiKey, model, provider, threadId, docIds, onEvent }) {
  const body = {
    query,
    user_id: userId,
  }

  if (apiKey?.trim()) body.api_key = apiKey.trim()
  if (model?.trim()) body.model = model.trim()
  if (provider?.trim()) body.provider = provider.trim()
  if (threadId) body.thread_id = threadId
  if (Array.isArray(docIds) && docIds.length) body.doc_ids = docIds

  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    },
    body: JSON.stringify(body),
  })

  if (!response.ok) return parseResponse(response)
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
        if (typeof data?.grounded === 'boolean') summary.grounded = data.grounded
      } else if (event === 'thread') {
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

export async function listThreads(userId) {
  const params = new URLSearchParams({ user_id: userId })
  const response = await fetch(`${API_BASE_URL}/threads?${params}`)
  return parseResponse(response)
}

export async function getThread(threadId, userId) {
  const params = new URLSearchParams({ user_id: userId })
  const response = await fetch(`${API_BASE_URL}/threads/${threadId}?${params}`)
  return parseResponse(response)
}

export async function deleteThread(threadId, userId) {
  const params = new URLSearchParams({ user_id: userId })
  const response = await fetch(`${API_BASE_URL}/threads/${threadId}?${params}`, {
    method: 'DELETE',
  })
  return parseResponse(response)
}

export async function renameThread(threadId, userId, title) {
  const params = new URLSearchParams({ user_id: userId })
  const response = await fetch(`${API_BASE_URL}/threads/${threadId}?${params}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  return parseResponse(response)
}

export async function ingest(file, userId, apiKey) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('user_id', userId)
  if (apiKey?.trim()) {
    formData.append('api_key', apiKey.trim())
  }

  const response = await fetch(`${API_BASE_URL}/ingest`, {
    method: 'POST',
    body: formData,
  })

  return parseResponse(response)
}

export async function generate(prompt) {
  const response = await fetch(`${API_BASE_URL}/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ prompt }),
  })

  return parseResponse(response)
}

export async function deleteDocument(userId, docId, apiKey) {
  const body = {
    user_id: userId,
    doc_id: docId,
  }

  if (apiKey?.trim()) {
    body.api_key = apiKey.trim()
  }

  const response = await fetch(`${API_BASE_URL}/delete`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })

  return parseResponse(response)
}

export async function getDocuments(userId) {
  const params = new URLSearchParams({ user_id: userId })
  const response = await fetch(`${API_BASE_URL}/documents?${params}`)
  return parseResponse(response)
}

export async function fetchModels(provider, apiKey) {
  const params = new URLSearchParams({ provider })
  if (apiKey?.trim()) params.append('api_key', apiKey.trim())
  const response = await fetch(`${API_BASE_URL}/models?${params}`)
  return parseResponse(response)
}

export async function deleteAllDocuments(userId, apiKey) {
  const body = {
    user_id: userId,
  }

  if (apiKey?.trim()) {
    body.api_key = apiKey.trim()
  }

  const response = await fetch(`${API_BASE_URL}/delete_all`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })

  return parseResponse(response)
}
