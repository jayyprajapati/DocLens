import { useRef, useState } from 'react'
import {
  Bot, ChevronLeft, ChevronRight, ExternalLink,
  Eye, EyeOff, FolderOpen, Info, KeyRound,
  MessageSquare, Moon, Plus, Sun, Trash2, Upload, X,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import './ThreadSidebar.css'

const PORTFOLIO_URL = 'https://github.com/jayyprajapati'

const PROVIDER_OPTIONS = [
  { value: 'openai',       label: 'OpenAI' },
  { value: 'anthropic',   label: 'Claude (Anthropic)' },
  { value: 'ollama_cloud', label: 'Ollama Cloud' },
]

const MODEL_SUGGESTIONS = {
  openai:       ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini', 'gpt-4.1', 'o4-mini'],
  anthropic:    ['claude-sonnet-4-6', 'claude-opus-4-8', 'claude-haiku-4-5-20251001'],
  ollama_cloud: ['gpt-oss:120b', 'gpt-oss:20b'],
}

const API_KEY_PLACEHOLDER = {
  openai:       'sk-... (OpenAI key)',
  anthropic:    'sk-ant-... (Anthropic key)',
  ollama_cloud: 'Ollama Cloud key',
  '':           'Select a provider first',
}

function formatRelativeTime(unixSeconds) {
  if (!unixSeconds) return ''
  const diff = Date.now() / 1000 - unixSeconds
  if (diff < 60)     return 'just now'
  if (diff < 3600)   return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400)  return `${Math.floor(diff / 3600)}h ago`
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`
  return new Date(unixSeconds * 1000).toLocaleDateString()
}

function getResourceTypeMeta(filename) {
  const ext = (filename || '').split('.').pop().toLowerCase()
  if (ext === 'pdf') return { label: 'PDF', cls: 'rtype-pdf' }
  if (ext === 'docx' || ext === 'doc') return { label: 'DOC', cls: 'rtype-docx' }
  if (ext === 'md' || ext === 'markdown') return { label: 'MD', cls: 'rtype-md' }
  return { label: 'FILE', cls: 'rtype-generic' }
}

function stripExtension(filename) {
  return (filename || '').replace(/\.[^.]+$/, '') || filename
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
  onToggle,
  theme,
  onThemeChange,
  userId,
  apiKey = '',
  model = '',
  provider = '',
  byokValidationMessage = '',
  onApiKeyChange,
  onModelChange,
  onProviderChange,
  onReset,
  resources = [],
  resourcesLoading = false,
  onResourceUpload,
  onResourceDelete,
}) {
  const [hoveredId, setHoveredId]           = useState(null)
  const [isApiKeyVisible, setIsApiKeyVisible] = useState(false)
  const isDark = theme === 'dark'
  const resourceInputRef = useRef(null)

  const handleResourceFileChange = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    await onResourceUpload?.(file)
    e.target.value = ''
  }

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

      <aside className={`thread-sidebar ${isOpen ? 'open' : 'closed'}`} aria-label="Sidebar">

        {/* ── Icon rail (collapsed, desktop only) ── */}
        <div className="sidebar-icon-rail" aria-hidden={isOpen}>
          <button
            type="button"
            className="rail-toggle-btn tooltip-r"
            onClick={onToggle}
            data-tooltip="Expand sidebar"
            aria-label="Expand sidebar"
          >
            <ChevronRight size={15} />
          </button>

          <div className="rail-icons-main">
            <button
              type="button"
              className="rail-icon-btn rail-new-chat tooltip-r"
              onClick={() => { onNewChat(); }}
              disabled={!canStartNewChat}
              data-tooltip="New chat"
              aria-label="New chat"
            >
              <Plus size={16} />
            </button>

            <div className="rail-thread-list" aria-label="Conversations">
              {threads.map((thread) => (
                <div
                  key={thread.id}
                  className={`rail-thread-item ${thread.id === activeThreadId ? 'active' : ''}`}
                >
                  <button
                    type="button"
                    className="rail-icon-btn rail-thread-btn tooltip-r"
                    onClick={() => handleSelectThread(thread.id)}
                    data-tooltip={thread.title || 'Untitled chat'}
                    aria-label={thread.title || 'Untitled chat'}
                  >
                    <MessageSquare size={15} />
                  </button>
                </div>
              ))}
            </div>

            <button
              type="button"
              className="rail-icon-btn tooltip-r"
              onClick={onToggle}
              data-tooltip="Resources"
              aria-label="Resources"
            >
              <FolderOpen size={16} />
            </button>
          </div>

          <div className="rail-icons-footer">
            <button
              type="button"
              className="rail-icon-btn tooltip-r"
              onClick={() => onThemeChange(isDark ? 'light' : 'dark')}
              data-tooltip={isDark ? 'Light mode' : 'Dark mode'}
              aria-label="Toggle theme"
            >
              {isDark ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>
        </div>

        {/* ── Full sidebar content ── */}
        <div className="sidebar-full-content thread-sidebar-inner">

          {/* Header */}
          <div className="thread-sidebar-header">
            <span className="thread-sidebar-title">
              <MessageSquare size={14} aria-hidden="true" className="sidebar-section-icon" />
              Conversations
            </span>
            <div className="thread-header-actions">
              <button
                type="button"
                className="thread-new-button"
                onClick={handleNewChat}
                disabled={!canStartNewChat}
                title="New chat"
                aria-label="Start a new chat"
              >
                <Plus size={13} aria-hidden="true" />
                New
              </button>
              <button
                type="button"
                className="sidebar-collapse-btn"
                onClick={onToggle}
                title="Collapse sidebar"
                aria-label="Collapse sidebar"
              >
                <ChevronLeft size={15} />
              </button>
              <button
                type="button"
                className="sidebar-close-btn"
                onClick={onClose}
                aria-label="Close panel"
              >
                <X size={15} />
              </button>
            </div>
          </div>

          {/* Thread list */}
          <ul className="thread-list">
            {threads.length === 0 && (
              <li className="thread-empty">
                Conversations will appear here after your first chat.
              </li>
            )}
            {threads.map((t) => {
              const isActive = t.id === activeThreadId
              const isHover  = t.id === hoveredId
              const isDraft  = Boolean(t.isDraft)
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
                    title={t.title || 'Untitled chat'}
                  >
                    <span className="thread-item-inner">
                      <MessageSquare size={12} className="thread-item-icon" aria-hidden="true" />
                      <span className="thread-item-title">{t.title || 'Untitled chat'}</span>
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
                      onClick={(e) => { e.stopPropagation(); onDelete(t.id) }}
                      title="Delete chat"
                      aria-label="Delete chat"
                    >
                      <Trash2 size={12} />
                    </button>
                  )}
                </li>
              )
            })}
          </ul>

          {/* Resources */}
          <div className="sidebar-resources">
            <div className="sidebar-resources-header">
              <span className="sidebar-resources-label">
                <FolderOpen size={14} aria-hidden="true" />
                Resources
                <button
                  type="button"
                  className="resource-info-btn tooltip-r tooltip-wide"
                  data-tooltip="Global resources are shared across every chat. Upload once, ask in any conversation."
                  aria-label="About resources"
                >
                  <Info size={17} />
                </button>
              </span>
              <div className="sidebar-resources-actions">
                <label
                  className="resource-upload-label"
                  title="Upload a shared document"
                  aria-label="Upload shared resource"
                >
                  <Upload size={11} aria-hidden="true" />
                  Upload
                  <input
                    ref={resourceInputRef}
                    type="file"
                    className="resource-upload-input"
                    onChange={handleResourceFileChange}
                    disabled={resourcesLoading}
                    accept=".pdf,.docx,.md,.markdown"
                  />
                </label>
              </div>
            </div>
            {resourcesLoading && <p className="resource-loading">Uploading…</p>}
            {!resourcesLoading && resources.length === 0 && (
              <p className="resource-empty">Upload PDF, DOCX, or Markdown files here to access them in any chat.</p>
            )}
            {resources.length > 0 && (
              <ul className="resource-list">
                {resources.map((doc) => {
                  const id   = doc.id || doc.doc_id
                  const name = doc.filename || doc.original_filename || id
                  const { label, cls } = getResourceTypeMeta(name)
                  const displayName = stripExtension(name)
                  return (
                    <li key={id} className="resource-item">
                      <span className={`resource-type-badge ${cls}`}>{label}</span>
                      <span className="resource-name" title={name}>{displayName}</span>
                      <button
                        type="button"
                        className="resource-delete"
                        onClick={() => onResourceDelete?.(id)}
                        title="Remove resource"
                        aria-label="Remove resource"
                      >
                        <X size={11} />
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          {/* API Settings — mobile only */}
          <div className="sidebar-api-settings">
            <div className="sidebar-section-label">API Settings</div>

            <div className="panel-field-group">
              <label className="field-label field-label-stack">Provider</label>
              <div className="control-row control-row-compact">
                <Bot size={15} className="control-leading-icon" aria-hidden="true" />
                <select
                  className="input compact-input"
                  value={provider}
                  aria-label="Provider"
                  onChange={(e) => { onProviderChange?.(e.target.value); onModelChange?.('') }}
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
                <KeyRound size={15} className="control-leading-icon" aria-hidden="true" />
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
                  {isApiKeyVisible ? <EyeOff size={13} /> : <Eye size={13} />}
                </button>
              </div>
            </div>

            <div className="panel-field-group">
              <label className="field-label field-label-stack">Model</label>
              <div className="control-row control-row-compact">
                <Bot size={15} className="control-leading-icon" aria-hidden="true" />
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

          {/* Footer */}
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
              <Link className="sidebar-link" to="/privacy">Privacy</Link>
              <span className="sidebar-link-dot">·</span>
              <Link className="sidebar-link" to="/terms">Terms</Link>
              <span className="sidebar-link-dot">·</span>
              <a
                className="sidebar-link"
                href={PORTFOLIO_URL}
                target="_blank"
                rel="noreferrer noopener"
              >
                Portfolio <ExternalLink size={10} />
              </a>
            </div>
          </div>

        </div>
      </aside>
    </>
  )
}
