// DocLens/frontend/src/services/auth.js

const STORAGE_KEY = 'doclens_user_id'

function base64urlEncode(str) {
  return btoa(unescape(encodeURIComponent(str)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '')
}

function getOrCreateUserId() {
  const existing = localStorage.getItem(STORAGE_KEY)
  if (existing) return existing
  const id = crypto.randomUUID()
  localStorage.setItem(STORAGE_KEY, id)
  return id
}

function mintToken(userId) {
  const header = base64urlEncode(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const payload = base64urlEncode(JSON.stringify({
    sub: userId,
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + 3600,
  }))
  return `${header}.${payload}.${base64urlEncode('dev')}`
}

let _cache = null

export function getUserId() {
  return getOrCreateUserId()
}

export function getAuthToken() {
  const userId = getOrCreateUserId()
  const now = Math.floor(Date.now() / 1000)
  if (_cache && _cache.userId === userId && _cache.exp > now + 60) return _cache.token
  const token = mintToken(userId)
  _cache = { userId, token, exp: now + 3500 }
  return token
}

export function getAuthHeaders() {
  return { Authorization: `Bearer ${getAuthToken()}` }
}
