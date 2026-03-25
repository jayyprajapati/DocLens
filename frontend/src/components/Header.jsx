import { useState } from 'react'
import { Bot, Eye, EyeOff, FileSearchCorner, Info, KeyRound } from 'lucide-react'
import InfoModal from './InfoModal'

const MODEL_OPTIONS = ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini']

function Header({ apiKey, model, usage, onApiKeyChange, onModelChange, onReset }) {
  const [activeModal, setActiveModal] = useState(null)
  const [isApiKeyVisible, setIsApiKeyVisible] = useState(false)

  const docsLimit = usage?.limits?.docs ?? 1
  const queriesLimit = usage?.limits?.queries
  const docsUsed = usage?.docs ?? 0
  const queriesUsed = usage?.queries ?? 0

  const closeModal = () => setActiveModal(null)

  const handleReset = async () => {
    await onReset()
    closeModal()
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
          <div className="byok-section" aria-label="BYOK model section">
            <div className="header-controls byok-controls">
              <div className="byok-title">BYOK Model</div>

              <div className="control-row">
                <KeyRound size={16} aria-hidden="true" className="control-leading-icon" />
                <div className="input-with-inline-action">
                  <input
                    id="api-key-input"
                    className="input input-key input-key-inline"
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
                <button
                  type="button"
                  className="icon-button icon-info"
                  onClick={() => setActiveModal('byok')}
                  aria-label="What is BYOK?"
                >
                  <Info size={18} />
                </button>
              </div>

              <div className="control-row">
                <Bot size={16} aria-hidden="true" className="control-leading-icon" />
                <select
                  id="model-select"
                  className="input input-model"
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
          </div>

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