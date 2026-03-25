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

export async function query(query, userId, apiKey, model) {
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

  const response = await fetch(`${API_BASE_URL}/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
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
