import { useEffect, useRef, useState } from 'react'
import { Bot, ChevronDown, Eye, EyeOff, FileSearchCorner, Info, KeyRound, RefreshCw } from 'lucide-react'
import InfoModal from './InfoModal'
import { fetchModels } from '../services/api'

const PROVIDER_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'ollama_cloud', label: 'Ollama Cloud' },
]

// Static suggestions shown before fetching / as fallback on error.
// Ollama Cloud: only the one confirmed-working model from the Cortex default.
const MODEL_SUGGESTIONS = {
  openai: ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini', 'gpt-4.1', 'o4-mini'],
  ollama_cloud: ['gpt-oss:120b'],
}

const API_KEY_PLACEHOLDER = {
  openai: 'sk-... (OpenAI key)',
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

  // Reset suggestions when provider changes.
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

  return (
    <>
      <header className="header">
        <div className="title-wrap">
          <FileSearchCorner className="title-icon" size={28} aria-hidden="true" />
          <div className="title-text-block">
            <h1 className="title">DocLens</h1>
            <p className="title-subtitle">Upload a document and chat with answers grounded in its content.</p>
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
              API Settings
              <ChevronDown size={16} aria-hidden="true" />
            </button>

            {openDropdown === 'byok' && (
              <div className="header-dropdown-panel byok-dropdown-panel" id="byok-dropdown-panel">
                <div className="byok-section" aria-label="API settings">
                  <div className="header-controls byok-controls">

                    {/* Provider */}
                    <div className="panel-field-group">
                      <div className="panel-label-row">
                        <label htmlFor="provider-select" className="field-label field-label-stack">Provider</label>
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
                          id="provider-select"
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

                    {/* API Key */}
                    <div className="panel-field-group">
                      <div className="panel-label-row">
                        <label htmlFor="api-key-input" className="field-label field-label-stack">API Key</label>
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
                          id="api-key-input"
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
                          title={isApiKeyVisible ? 'Hide key' : 'Show key'}
                        >
                          {isApiKeyVisible ? <EyeOff size={14} /> : <Eye size={14} />}
                        </button>
                      </div>
                    </div>

                    {/* Model — free-text input with datalist suggestions */}
                    <div className="panel-field-group">
                      <div className="panel-label-row">
                        <label htmlFor="model-input" className="field-label field-label-stack">Model</label>
                        <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
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
                          id="model-input"
                          list="model-datalist"
                          className="input input-model compact-input"
                          value={model}
                          placeholder={provider ? 'Type or select a model...' : 'Select a provider first'}
                          disabled={!provider}
                          autoComplete="off"
                          onChange={(e) => onModelChange(e.target.value)}
                        />
                        <datalist id="model-datalist">
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
                        <p className="byok-inline-error" style={{ color: 'var(--color-text-muted, #888)', marginTop: '4px' }}>
                          {isFetchingModels
                            ? 'Fetching available models...'
                            : 'Click ↻ to load your available Ollama Cloud models.'}
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
          <li><strong>Ollama Cloud</strong> — key from <strong>ollama.com</strong>.</li>
        </ul>
        <p>Your key is stored only in your browser and is never saved to any DocLens server. It is cleared when you reset your session.</p>
      </InfoModal>

      <InfoModal isOpen={activeModal === 'model'} onClose={closeModal} title="About Models">
        <p>Type any model name or pick from the suggestions. For Ollama Cloud, click the ↻ button to load your account&apos;s actual available models.</p>
        <p><strong>OpenAI</strong> — billed to your OpenAI account:</p>
        <ul>
          <li><code>gpt-4o-mini</code> — fast and cost-efficient.</li>
          <li><code>gpt-4o</code> — stronger reasoning.</li>
          <li><code>gpt-4.1-mini</code> / <code>gpt-4.1</code> — latest generation.</li>
          <li><code>o4-mini</code> — reasoning-focused.</li>
        </ul>
        <p><strong>Ollama Cloud</strong> — billed to your Ollama account:</p>
        <ul>
          <li><code>gpt-oss:120b</code> — confirmed default model. Click ↻ to see all models available in your account.</li>
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
