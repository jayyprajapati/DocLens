import { useState } from 'react'
import { Files, Info, KeyRound } from 'lucide-react'
import InfoModal from './InfoModal'

const MODEL_OPTIONS = ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini']

function Header({ apiKey, model, onApiKeyChange, onModelChange, onReset }) {
  const [activeModal, setActiveModal] = useState(null)

  const closeModal = () => setActiveModal(null)

  const handleReset = async () => {
    await onReset()
    closeModal()
  }

  return (
    <>
      <header className="header">
        <div className="title-wrap">
          <h1 className="title">
            <Files className="title-icon" size={20} aria-hidden="true" />
            <span>DocLens</span>
          </h1>
          <p className="title-subtitle">A focused workspace for document-grounded chat</p>
        </div>

        <div className="header-main-controls">
          <div className="byok-section" aria-label="BYOK model section">
            <div className="byok-title">BYOK Model</div>

            <div className="header-controls byok-controls">
              <div className="field-group key-group">
                <label className="field-label" htmlFor="api-key-input">
                  <KeyRound size={15} aria-hidden="true" />
                  <span>Ollama key</span>
                  <button
                    type="button"
                    className="icon-button icon-info"
                    onClick={() => setActiveModal('byok')}
                    aria-label="What is BYOK?"
                  >
                    <Info size={18} />
                  </button>
                </label>
                <input
                  id="api-key-input"
                  className="input input-key"
                  type="password"
                  value={apiKey}
                  placeholder="Enter your Ollama key"
                  onChange={(event) => onApiKeyChange(event.target.value)}
                />
              </div>

              <div className="field-group">
                <label className="field-label" htmlFor="model-select">
                  <span>Model</span>
                  <button
                    type="button"
                    className="icon-button icon-info"
                    onClick={() => setActiveModal('model')}
                    aria-label="Model information"
                  >
                    <Info size={18} />
                  </button>
                </label>
                <select
                  id="model-select"
                  className="input input-model"
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
          </div>

          <div className="header-reset-wrap">
            <button type="button" className="button button-reset" onClick={() => setActiveModal('reset')}>
              Reset
            </button>
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