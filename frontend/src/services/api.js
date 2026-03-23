const API_BASE_URL = 'http://localhost:8001'

async function parseResponse(response) {
  const contentType = response.headers.get('content-type') || ''
  const isJson = contentType.includes('application/json')
  const payload = isJson ? await response.json() : await response.text()

  if (!response.ok) {
    const message =
      (isJson && payload?.detail) ||
      (typeof payload === 'string' && payload) ||
      `Request failed with status ${response.status}`
    throw new Error(message)
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

export async function ingest(file, userId) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('user_id', userId)

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