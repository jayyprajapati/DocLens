const MODEL_OPTIONS = ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini']

function Header({ apiKey, model, onApiKeyChange, onModelChange, onReset }) {
  return (
    <header className="header">
      <h1 className="title">DocLens</h1>

      <div className="header-controls">
        <input
          className="input input-key"
          type="password"
          value={apiKey}
          placeholder="API key"
          onChange={(event) => onApiKeyChange(event.target.value)}
        />

        <select
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

        <button type="button" className="button button-text" onClick={onReset}>
          Reset
        </button>
      </div>
    </header>
  )
}

export default Header