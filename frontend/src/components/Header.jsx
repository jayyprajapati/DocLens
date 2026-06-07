import { useEffect, useRef, useState } from 'react'
import { Bot, ChevronDown, Eye, EyeOff, FileSearch, Info, KeyRound, RefreshCw, Settings2 } from 'lucide-react'
import InfoModal from './InfoModal'
import { fetchModels } from '../services/api'

const PROVIDER_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Claude (Anthropic)' },
  { value: 'ollama_cloud', label: 'Ollama Cloud' },
]

const MODEL_SUGGESTIONS = {
  openai: ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini', 'gpt-4.1', 'o4-mini'],
  anthropic: ['claude-sonnet-4-6', 'claude-opus-4-8', 'claude-haiku-4-5-20251001'],
  ollama_cloud: ['gpt-oss:120b', 'gpt-oss:20b'],
}

const API_KEY_PLACEHOLDER = {
  openai: 'sk-... (OpenAI key)',
  anthropic: 'sk-ant-... (Anthropic key)',
  ollama_cloud: 'Ollama Cloud key',
  '': 'Select a provider first',
}

function Header({
  apiKey,
  model,
  provider,
  byokValidationMessage,
  onApiKeyChange,
  onModelChange,
  onProviderChange,
  onReset,
}) {
  const [activeModal, setActiveModal] = useState(null)
  const [isApiKeyVisible, setIsApiKeyVisible] = useState(false)
  const [openDropdown, setOpenDropdown] = useState(null)
  const [modelSuggestions, setModelSuggestions] = useState(MODEL_SUGGESTIONS[provider] || [])
  const [isFetchingModels, setIsFetchingModels] = useState(false)
  const [modelFetchError, setModelFetchError] = useState(null)
  const byokDropdownRef = useRef(null)

  const closeModal = () => setActiveModal(null)

  useEffect(() => {
    setModelSuggestions(MODEL_SUGGESTIONS[provider] || [])
    setModelFetchError(null)
  }, [provider])

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (byokDropdownRef.current?.contains(event.target)) return
      setOpenDropdown(null)
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleReset = async () => {
    await onReset()
    closeModal()
    setOpenDropdown(null)
  }

  const handleFetchModels = async () => {
    if (!provider || !apiKey.trim() || isFetchingModels) return
    setIsFetchingModels(true)
    setModelFetchError(null)
    try {
      const data = await fetchModels(provider, apiKey)
      const models = data?.models || []
      if (models.length > 0) {
        setModelSuggestions(models)
      } else {
        setModelFetchError('No models returned. Check your API key.')
      }
    } catch (err) {
      setModelFetchError(err?.message || 'Could not fetch models.')
    } finally {
      setIsFetchingModels(false)
    }
  }

  const canFetchModels = provider === 'ollama_cloud' && apiKey.trim().length > 0

  const renderByokFields = (idSuffix = '') => (
    <div className="header-controls byok-controls">
      <div className="panel-field-group">
        <div className="panel-label-row">
          <label htmlFor={`provider-select${idSuffix}`} className="field-label">Provider</label>
          <button
            type="button"
            className="icon-button icon-info"
            onClick={() => setActiveModal('byok')}
            aria-label="About providers"
          >
            <Info size={18} />
          </button>
        </div>
        <div className="control-row control-row-compact">
          <Bot size={16} aria-hidden="true" className="control-leading-icon" />
          <select
            id={`provider-select${idSuffix}`}
            className="input input-model compact-input"
            aria-label="Provider"
            value={provider}
            onChange={(e) => {
              onProviderChange(e.target.value)
              onModelChange('')
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
        <div className="panel-label-row">
          <label htmlFor={`api-key-input${idSuffix}`} className="field-label">API Key</label>
          <button
            type="button"
            className="icon-button icon-info"
            onClick={() => setActiveModal('byok')}
            aria-label="About API keys"
          >
            <Info size={18} />
          </button>
        </div>
        <div className="control-row control-row-compact">
          <KeyRound size={16} aria-hidden="true" className="control-leading-icon" />
          <input
            id={`api-key-input${idSuffix}`}
            className="input compact-input compact-input-key"
            type={isApiKeyVisible ? 'text' : 'password'}
            value={apiKey}
            placeholder={API_KEY_PLACEHOLDER[provider] ?? 'Enter your API key'}
            aria-label="API key"
            onChange={(e) => onApiKeyChange(e.target.value)}
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
        <div className="panel-label-row">
          <label htmlFor={`model-input${idSuffix}`} className="field-label">Model</label>
          <div className="panel-label-actions">
            {canFetchModels && (
              <button
                type="button"
                className="icon-button icon-info"
                onClick={handleFetchModels}
                disabled={isFetchingModels}
                aria-label="Fetch available models from Ollama Cloud"
                title="Fetch available models"
              >
                <RefreshCw size={16} className={isFetchingModels ? 'spin' : ''} />
              </button>
            )}
            <button
              type="button"
              className="icon-button icon-info"
              onClick={() => setActiveModal('model')}
              aria-label="Model information"
            >
              <Info size={18} />
            </button>
          </div>
        </div>
        <div className="control-row control-row-compact">
          <Bot size={16} aria-hidden="true" className="control-leading-icon" />
          <input
            id={`model-input${idSuffix}`}
            list={`model-datalist${idSuffix}`}
            className="input input-model compact-input"
            value={model}
            placeholder={provider ? 'Type or select a model...' : 'Select a provider first'}
            disabled={!provider}
            autoComplete="off"
            onChange={(e) => onModelChange(e.target.value)}
          />
          <datalist id={`model-datalist${idSuffix}`}>
            {modelSuggestions.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </div>
        {modelFetchError && (
          <p className="byok-inline-error" role="alert" style={{ marginTop: '4px' }}>
            {modelFetchError}
          </p>
        )}
        {canFetchModels && !modelFetchError && (
          <p className="byok-inline-error" style={{ color: 'var(--text3)', marginTop: '4px' }}>
            {isFetchingModels
              ? 'Fetching available models...'
              : 'Click the refresh icon to load your available Ollama Cloud models.'}
          </p>
        )}
      </div>

      {byokValidationMessage && (
        <p className="byok-inline-error" role="alert">
          {byokValidationMessage}
        </p>
      )}

      <div className="reset-divider" aria-hidden="true" />
      <button type="button" className="button button-reset" onClick={() => setActiveModal('reset')}>
        Reset session
      </button>
    </div>
  )

  return (
    <>
      <header className="header">
        <div className="title-wrap">
          <span className="title-icon" aria-hidden="true">
            <FileSearch size={18} strokeWidth={2} />
          </span>
          <div className="title-text-block">
            <h1 className="title">DocLens</h1>
            <span className="title-subtitle">Cited document answers</span>
          </div>
        </div>

        <div className="header-main-controls">
          <div className="header-dropdown" ref={byokDropdownRef}>
            <button
              type="button"
              className="header-dropdown-trigger"
              onClick={() => setOpenDropdown((prev) => (prev === 'byok' ? null : 'byok'))}
              aria-expanded={openDropdown === 'byok'}
              aria-controls="byok-dropdown-panel"
            >
              <Settings2 size={15} aria-hidden="true" />
              Settings
              <ChevronDown size={14} aria-hidden="true" />
            </button>

            {openDropdown === 'byok' && (
              <div className="header-dropdown-panel byok-dropdown-panel" id="byok-dropdown-panel">
                <div className="byok-section" aria-label="API settings">
                  {renderByokFields()}
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      <InfoModal isOpen={activeModal === 'byok'} onClose={closeModal} title="Provider &amp; API Key">
        <p>DocLens requires your own API key. Select the provider that matches your key:</p>
        <ul>
          <li><strong>OpenAI</strong> — key from <strong>platform.openai.com</strong> (starts with <code>sk-</code>).</li>
          <li><strong>Claude (Anthropic)</strong> — key from <strong>console.anthropic.com</strong> (starts with <code>sk-ant-</code>).</li>
          <li><strong>Ollama Cloud</strong> — key from <strong>ollama.com</strong>.</li>
        </ul>
        <p>Your key is stored only in your browser and is sent per request to power your chats — it is never saved to any DocLens or Brain server, and there is no shared fallback key. It is cleared when you reset your session.</p>
      </InfoModal>

      <InfoModal isOpen={activeModal === 'model'} onClose={closeModal} title="About Models">
        <p>Type any model name or pick from the suggestions. For Ollama Cloud, click the refresh button to load your account&apos;s actual available models.</p>
        <p><strong>OpenAI</strong> — billed to your OpenAI account:</p>
        <ul>
          <li><code>gpt-4o-mini</code> — fast and cost-efficient.</li>
          <li><code>gpt-4o</code> — stronger reasoning.</li>
          <li><code>gpt-4.1-mini</code> / <code>gpt-4.1</code> — latest generation.</li>
          <li><code>o4-mini</code> — reasoning-focused.</li>
        </ul>
        <p><strong>Ollama Cloud</strong> — billed to your Ollama account:</p>
        <ul>
          <li><code>gpt-oss:120b</code> — confirmed default model. Click the refresh icon to see all models available in your account.</li>
        </ul>
      </InfoModal>

      <InfoModal
        isOpen={activeModal === 'reset'}
        onClose={closeModal}
        title="Reset Session"
        footer={
          <button type="button" className="button button-reset" onClick={handleReset}>
            Reset now
          </button>
        }
      >
        <p>Reset clears your session history, uploaded documents, and API key from the browser.</p>
        <p>You will need to enter your API key again after resetting.</p>
      </InfoModal>
    </>
  )
}

export default Header
