import { useState } from 'react'
import { Info, KeyRound } from 'lucide-react'
import InfoModal from './InfoModal'

const MODEL_OPTIONS = ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini']

function Header({ apiKey, model, onApiKeyChange, onModelChange, onReset }) {
  const [activeModal, setActiveModal] = useState(null)

  const closeModal = () => setActiveModal(null)

  const handleReset = () => {
    onReset()
    closeModal()
  }

  return (
    <>
      <header className="header">
        <div className="title-wrap">
          <h1 className="title">DocLens</h1>
          <p className="title-subtitle">A focused workspace for document-grounded chat</p>
        </div>

        <div className="header-controls">
          <div className="field-group key-group">
            <label className="field-label" htmlFor="api-key-input">
              <KeyRound size={14} aria-hidden="true" />
              <span>API key</span>
              <button
                type="button"
                className="icon-button icon-info"
                onClick={() => setActiveModal('byok')}
                aria-label="What is BYOK?"
              >
                <Info size={14} />
              </button>
            </label>
            <input
              id="api-key-input"
              className="input input-key"
              type="password"
              value={apiKey}
              placeholder="Enter your OpenAI key"
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
                <Info size={14} />
              </button>
            </label>
            <select
              id="model-select"
              className="input input-model"
              value={model}
              onChange={(event) => onModelChange(event.target.value)}
            >
              {MODEL_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>

          <div className="field-group field-reset">
            <div className="field-label field-label-reset">
              <span>Session</span>
              <button
                type="button"
                className="icon-button icon-info"
                onClick={() => setActiveModal('reset')}
                aria-label="Reset details"
              >
                <Info size={14} />
              </button>
            </div>
            <button type="button" className="button button-text" onClick={onReset}>
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
          <button type="button" className="button button-modal" onClick={handleReset}>
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