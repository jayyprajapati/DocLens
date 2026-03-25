import { useEffect, useRef, useState } from 'react'
import { Bot, ChevronDown, Eye, EyeOff, FileSearchCorner, Info, KeyRound } from 'lucide-react'
import InfoModal from './InfoModal'

const MODEL_OPTIONS = ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini']

function Header({
  isBYOKEnabled,
  isBYOKForced,
  apiKey,
  model,
  usage,
  byokValidationMessage,
  onToggleBYOK,
  onApiKeyChange,
  onModelChange,
  onReset,
}) {
  const [activeModal, setActiveModal] = useState(null)
  const [isApiKeyVisible, setIsApiKeyVisible] = useState(false)
  const [openDropdown, setOpenDropdown] = useState(null)
  const byokDropdownRef = useRef(null)
  const usageDropdownRef = useRef(null)

  const docsLimit = usage?.limits?.docs ?? 1
  const queriesLimit = usage?.limits?.queries
  const docsUsed = usage?.docs ?? 0
  const queriesUsed = usage?.queries ?? 0

  const closeModal = () => setActiveModal(null)

  useEffect(() => {
    const handleClickOutside = (event) => {
      const target = event.target
      if (byokDropdownRef.current?.contains(target) || usageDropdownRef.current?.contains(target)) {
        return
      }

      setOpenDropdown(null)
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  const handleReset = async () => {
    await onReset()
    closeModal()
    setOpenDropdown(null)
  }

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
              BYOK Model
              <ChevronDown size={16} aria-hidden="true" />
            </button>

            {openDropdown === 'byok' && (
              <div className="header-dropdown-panel byok-dropdown-panel" id="byok-dropdown-panel">
                <div className="byok-section" aria-label="BYOK model section">
                  <div className="header-controls byok-controls">
                    <div className="byok-toggle-row">
                      <span className="byok-toggle-label">Enable BYOK</span>
                      <label className="switch" aria-label="Enable BYOK">
                        <input
                          type="checkbox"
                          checked={isBYOKEnabled}
                          disabled={isBYOKForced}
                          onChange={(event) => onToggleBYOK(event.target.checked)}
                        />
                        <span className="slider" />
                      </label>
                    </div>

                    {isBYOKForced && (
                      <div className="byok-forced-note" role="status" aria-live="polite">
                        <Info size={14} aria-hidden="true" />
                        <span>Free quota exhausted. Please use your API key.</span>
                      </div>
                    )}

                    <div className="panel-field-group">
                      <div className="panel-label-row">
                        <label htmlFor="api-key-input" className="field-label field-label-stack">API Key</label>
                        <button
                          type="button"
                          className="icon-button icon-info"
                          onClick={() => setActiveModal('byok')}
                          aria-label="What is BYOK?"
                        >
                          <Info size={18} />
                        </button>
                      </div>

                      <div className="control-row control-row-compact">
                        <KeyRound size={16} aria-hidden="true" className="control-leading-icon" />
                        <div className="input-with-inline-action compact-input-wrap">
                          <input
                            id="api-key-input"
                            className="input input-key input-key-inline compact-input compact-input-key"
                            type={isApiKeyVisible ? 'text' : 'password'}
                            value={apiKey}
                            placeholder="Enter your Ollama key"
                            aria-label="Ollama key"
                            onChange={(event) => onApiKeyChange(event.target.value)}
                          />
                          <button
                            type="button"
                            className="inline-input-action"
                            onClick={() => setIsApiKeyVisible((previousValue) => !previousValue)}
                            aria-label={isApiKeyVisible ? 'Hide key' : 'Show key'}
                            title={isApiKeyVisible ? 'Hide key' : 'Show key'}
                          >
                            {isApiKeyVisible ? <EyeOff size={16} /> : <Eye size={16} />}
                          </button>
                        </div>
                      </div>
                    </div>

                    <div className="panel-field-group">
                      <div className="panel-label-row">
                        <label htmlFor="model-select" className="field-label field-label-stack">Model</label>
                        <button
                          type="button"
                          className="icon-button icon-info"
                          onClick={() => setActiveModal('model')}
                          aria-label="Model information"
                        >
                          <Info size={18} />
                        </button>
                      </div>

                      <div className="control-row control-row-compact">
                        <Bot size={16} aria-hidden="true" className="control-leading-icon" />
                        <select
                          id="model-select"
                          className="input input-model compact-input"
                          aria-label="Model"
                          value={model}
                          onChange={(event) => onModelChange(event.target.value)}
                        >
                          <option value="">Select model</option>
                          {MODEL_OPTIONS.map((option) => (
                            <option key={option} value={option}>
                              {option}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>

                    {isBYOKEnabled && byokValidationMessage && (
                      <p className="byok-inline-error" role="alert">
                        {byokValidationMessage}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="header-dropdown" ref={usageDropdownRef}>
            <button
              type="button"
              className="header-dropdown-trigger"
              onClick={() => setOpenDropdown((prev) => (prev === 'usage' ? null : 'usage'))}
              aria-expanded={openDropdown === 'usage'}
              aria-controls="usage-dropdown-panel"
            >
              Usage
              <ChevronDown size={16} aria-hidden="true" />
            </button>

            {openDropdown === 'usage' && (
              <div className="header-dropdown-panel usage-dropdown-panel" id="usage-dropdown-panel">
                <div className="header-reset-wrap">
                  <div className="reset-usage-stack" aria-live="polite">
                    <div className="usage-line">Docs: {docsUsed} / {docsLimit}</div>
                    <div className="usage-line">
                      {queriesLimit == null
                        ? 'Queries: unlimited'
                        : `Queries: ${queriesUsed} / ${queriesLimit}`}
                    </div>
                    <div className="reset-divider" aria-hidden="true" />
                    <button type="button" className="button button-reset" onClick={() => setActiveModal('reset')}>
                      Reset
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      <InfoModal isOpen={activeModal === 'byok'} onClose={closeModal} title="Bring Your Own Key (BYOK)">
        <p>
          BYOK means you provide your own API key to call the model provider directly from your
          session.
        </p>
        <p>
          DocLens does not store your key on a backend database, and your key is cleared when the
          page refreshes.
        </p>
        <p>
          Benefits: your own rate limits, direct billing visibility, and control over which model
          runs each answer.
        </p>
      </InfoModal>

      <InfoModal isOpen={activeModal === 'model'} onClose={closeModal} title="About Models">
        <p>
          Models are the reasoning engines behind answers. Different models trade off speed, cost,
          and depth.
        </p>
        <ul>
          <li>gpt-4o-mini: fastest and efficient for lightweight Q&A.</li>
          <li>gpt-4o: stronger reasoning for harder document questions.</li>
          <li>gpt-4.1-mini: balanced quality with steady latency.</li>
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
        <p>Reset clears your current session history and uploaded document context.</p>
        <p>
          Any free usage progress is removed, and you may need to provide an API key again before
          asking more questions.
        </p>
      </InfoModal>
    </>
  )
}

export default Header