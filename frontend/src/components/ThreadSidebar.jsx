import { useState } from 'react'
import { Bot, ExternalLink, Eye, EyeOff, KeyRound, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import './ThreadSidebar.css'

const PORTFOLIO_URL = 'https://github.com/jayyprajapati'

const PROVIDER_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'ollama_cloud', label: 'Ollama Cloud' },
]

const MODEL_SUGGESTIONS = {
  openai: ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini', 'gpt-4.1', 'o4-mini'],
  ollama_cloud: ['gpt-oss:120b'],
}

const API_KEY_PLACEHOLDER = {
  openai: 'sk-... (OpenAI key)',
  ollama_cloud: 'Ollama Cloud key',
  '': 'Select a provider first',
}

function formatRelativeTime(unixSeconds) {
  if (!unixSeconds) return ''
  const diff = Date.now() / 1000 - unixSeconds
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`
  return new Date(unixSeconds * 1000).toLocaleDateString()
}

export default function ThreadSidebar({
  threads,
  activeThreadId,
  onSelect,
  onNewChat,
  canStartNewChat = true,
  onDelete,
  isOpen,
  onClose,
  theme,
  onThemeChange,
  userId,
  // API settings (mobile only)
  apiKey = '',
  model = '',
  provider = '',
  byokValidationMessage = '',
  onApiKeyChange,
  onModelChange,
  onProviderChange,
  onReset,
}) {
  const [hoveredId, setHoveredId] = useState(null)
  const [isApiKeyVisible, setIsApiKeyVisible] = useState(false)
  const isDark = theme === 'dark'

  const handleSelectThread = (id) => {
    onSelect(id)
    if (window.innerWidth <= 768) onClose()
  }

  const handleNewChat = () => {
    onNewChat()
    if (window.innerWidth <= 768) onClose()
  }

  const handleReset = () => {
    if (window.confirm('Reset clears your session, documents, and API key. Continue?')) {
      onReset?.()
    }
  }

  return (
    <>
      {isOpen && (
        <div className="sidebar-backdrop" onClick={onClose} aria-hidden="true" />
      )}

      <aside className={`thread-sidebar ${isOpen ? 'open' : 'closed'}`} aria-hidden={!isOpen}>
        <div className="thread-sidebar-inner">
          <div className="thread-sidebar-header">
            <span className="thread-sidebar-title">Conversations</span>
            <div className="thread-header-actions">
              <button
                type="button"
                className="thread-new-button"
                onClick={handleNewChat}
                disabled={!canStartNewChat}
                title="Start a new chat"
              >
                New
              </button>
              <button
                type="button"
                className="sidebar-close-btn"
                onClick={onClose}
                aria-label="Close panel"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          <ul className="thread-list">
            {threads.length === 0 && (
              <li className="thread-empty">New conversations will appear here after your first question.</li>
            )}
            {threads.map((t) => {
              const isActive = t.id === activeThreadId
              const isHover = t.id === hoveredId
              const isDraft = Boolean(t.isDraft)
              return (
                <li
                  key={t.id}
                  className={`thread-item ${isActive ? 'active' : ''} ${isDraft ? 'draft' : ''}`}
                  onMouseEnter={() => setHoveredId(t.id)}
                  onMouseLeave={() => setHoveredId(null)}
                >
                  <button
                    type="button"
                    className="thread-select"
                    onClick={() => handleSelectThread(t.id)}
                  >
                    <span className="thread-item-title">
                      {t.title || 'Untitled chat'}
                    </span>
                    <span className="thread-item-meta">
                      {isDraft
                        ? 'Draft conversation'
                        : `${t.message_count ? `${t.message_count} msgs · ` : ''}${formatRelativeTime(t.updated_at)}`}
                    </span>
                  </button>
                  {!isDraft && (isHover || isActive) && (
                    <button
                      type="button"
                      className="thread-delete"
                      onClick={(e) => {
                        e.stopPropagation()
                        onDelete(t.id)
                      }}
                      title="Delete chat"
                      aria-label="Delete chat"
                    >
                      ×
                    </button>
                  )}
                </li>
              )
            })}
          </ul>

          {/* API Settings — only shown on mobile via CSS */}
          <div className="sidebar-api-settings">
            <div className="sidebar-section-label">API Settings</div>

            <div className="panel-field-group">
              <label className="field-label field-label-stack">Provider</label>
              <div className="control-row control-row-compact">
                <Bot size={16} className="control-leading-icon" aria-hidden="true" />
                <select
                  className="input compact-input"
                  value={provider}
                  aria-label="Provider"
                  onChange={(e) => {
                    onProviderChange?.(e.target.value)
                    onModelChange?.('')
                  }}
                >
                  <option value="">Select provider</option>
                  {PROVIDER_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="panel-field-group">
              <label className="field-label field-label-stack">API Key</label>
              <div className="control-row control-row-compact">
                <KeyRound size={16} className="control-leading-icon" aria-hidden="true" />
                <input
                  className="input compact-input compact-input-key"
                  type={isApiKeyVisible ? 'text' : 'password'}
                  value={apiKey}
                  placeholder={API_KEY_PLACEHOLDER[provider] ?? 'Enter your API key'}
                  aria-label="API key"
                  onChange={(e) => onApiKeyChange?.(e.target.value)}
                />
                <button
                  type="button"
                  className="eye-toggle-btn"
                  onClick={() => setIsApiKeyVisible((v) => !v)}
                  aria-label={isApiKeyVisible ? 'Hide key' : 'Show key'}
                >
                  {isApiKeyVisible ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            <div className="panel-field-group">
              <label className="field-label field-label-stack">Model</label>
              <div className="control-row control-row-compact">
                <Bot size={16} className="control-leading-icon" aria-hidden="true" />
                <input
                  list="sidebar-model-datalist"
                  className="input compact-input"
                  value={model}
                  placeholder={provider ? 'Type or select a model...' : 'Select a provider first'}
                  disabled={!provider}
                  autoComplete="off"
                  onChange={(e) => onModelChange?.(e.target.value)}
                />
                <datalist id="sidebar-model-datalist">
                  {(MODEL_SUGGESTIONS[provider] || []).map((m) => (
                    <option key={m} value={m} />
                  ))}
                </datalist>
              </div>
            </div>

            {byokValidationMessage && (
              <p className="byok-inline-error" role="alert">{byokValidationMessage}</p>
            )}

            <div className="reset-divider" aria-hidden="true" />
            <button type="button" className="button button-reset" onClick={handleReset}>
              Reset session
            </button>
          </div>

          <div className="sidebar-footer">
            <div className="sidebar-footer-row sidebar-theme-row">
              <span className="sidebar-footer-label">Dark mode</span>
              <button
                type="button"
                role="switch"
                aria-checked={isDark}
                className={`theme-switch ${isDark ? 'on' : ''}`}
                onClick={() => onThemeChange(isDark ? 'light' : 'dark')}
                aria-label="Toggle dark mode"
              >
                <span className="theme-switch-thumb" />
              </button>
            </div>

            {userId && (
              <div className="sidebar-footer-row">
                <span className="sidebar-footer-label">Session</span>
                <span className="sidebar-session-id" title={userId}>{userId.slice(0, 8)}…</span>
              </div>
            )}

            <div className="sidebar-links">
              <Link className="sidebar-link" to="/privacy">Privacy Policy</Link>
              <Link className="sidebar-link" to="/terms">Terms of Use</Link>
              <a
                className="sidebar-link"
                href={PORTFOLIO_URL}
                target="_blank"
                rel="noreferrer noopener"
              >
                Portfolio <ExternalLink size={11} />
              </a>
            </div>
          </div>
        </div>
      </aside>
    </>
  )
}
