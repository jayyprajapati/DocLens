// DocLens/frontend/src/services/auth.js
//
// Anonymous, server-signed sessions. The backend mints the user id and signs it (POST /session);
// we keep the token in localStorage and send it as a bearer token. Browsers from before signed
// sessions hold only a self-generated id — it is sent once as `legacy_token` so the server can
// sign that same id and the user keeps their chats and documents.

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')
const SESSION_KEY = 'doclens_session'
const USER_KEY = 'doclens_user_id'

function base64urlEncode(str) {
  return btoa(unescape(encodeURIComponent(str)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '')
}

// The old self-minted token shape, used only to upgrade an existing id.
function legacyToken() {
  const id = localStorage.getItem(USER_KEY)
  if (!id) return null
  const header = base64urlEncode(JSON.stringify({ alg: 'none', typ: 'JWT' }))
  const payload = base64urlEncode(JSON.stringify({ sub: id }))
  return `${header}.${payload}.legacy`
}

let pending = null

export async function ensureSession(force = false) {
  if (!force) {
    const existing = localStorage.getItem(SESSION_KEY)
    if (existing) return existing
  }
  if (pending) return pending
  pending = fetch(`${API_BASE_URL}/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ legacy_token: legacyToken() }),
  })
    .then(async (r) => {
      if (!r.ok) {
        const body = await r.json().catch(() => ({}))
        const err = new Error(body?.detail || 'Could not start a session.')
        err.status = r.status
        throw err
      }
      return r.json()
    })
    .then((data) => {
      localStorage.setItem(SESSION_KEY, data.token)
      localStorage.setItem(USER_KEY, data.user_id)
      return data.token
    })
    .finally(() => { pending = null })
  return pending
}

export function getUserId() {
  return localStorage.getItem(USER_KEY) || ''
}

export async function getAuthHeaders(force = false) {
  return { Authorization: `Bearer ${await ensureSession(force)}` }
}
