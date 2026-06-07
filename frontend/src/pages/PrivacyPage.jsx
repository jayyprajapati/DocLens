import { ArrowLeft, Database, KeyRound, ShieldCheck, Timer } from 'lucide-react'
import { Link } from 'react-router-dom'

function PrivacyPage() {
  return (
    <div className="legal-page">
      <div className="legal-shell">
        <header className="legal-header">
          <div className="legal-header-topline">
            <p className="legal-kicker">Privacy policy</p>
            <Link className="legal-back-link" to="/">
              <ArrowLeft size={16} aria-hidden="true" />
              <span>Back to DocLens</span>
            </Link>
          </div>
          <h1>
            <span className="legal-title-line">Your documents,</span>
            <span className="legal-title-highlight">handled with clarity.</span>
          </h1>
          <p className="legal-intro">
            This policy explains what DocLens processes, how document-grounded answers are produced,
            and the controls you have over files, chats, and API credentials.
          </p>
          <p className="legal-meta">Last updated · March 2026</p>
        </header>

        <div className="legal-summary" aria-label="Privacy summary">
          <div className="legal-summary-item">
            <span className="legal-summary-icon"><Timer size={18} aria-hidden="true" /></span>
            <div className="legal-summary-copy">
              <span className="legal-summary-value">24 hour expiry</span>
              <span className="legal-summary-label">Documents are temporary and can be deleted sooner.</span>
            </div>
          </div>
          <div className="legal-summary-item">
            <span className="legal-summary-icon"><KeyRound size={18} aria-hidden="true" /></span>
            <div className="legal-summary-copy">
              <span className="legal-summary-value">Your key stays yours</span>
              <span className="legal-summary-label">BYOK credentials remain in your browser session.</span>
            </div>
          </div>
          <div className="legal-summary-item">
            <span className="legal-summary-icon"><ShieldCheck size={18} aria-hidden="true" /></span>
            <div className="legal-summary-copy">
              <span className="legal-summary-value">You stay in control</span>
              <span className="legal-summary-label">Delete resources, chats, or reset the full session.</span>
            </div>
          </div>
        </div>

        <section className="legal-section">
          <div className="legal-section-heading">
            <span className="legal-section-index">01</span>
            <span className="legal-section-icon"><Database size={18} aria-hidden="true" /></span>
            <h2>What we process</h2>
          </div>
          <p>DocLens processes only the information required to run document Q&amp;A and keep chats separated.</p>
          <ul>
            <li>Uploaded PDF, DOCX, and Markdown content.</li>
            <li>Questions, cited answers, and conversation history.</li>
            <li>Session identifiers and basic usage counters.</li>
          </ul>
        </section>

        <section className="legal-section">
          <div className="legal-section-heading">
            <span className="legal-section-index">02</span>
            <span className="legal-section-icon"><ShieldCheck size={18} aria-hidden="true" /></span>
            <h2>How it is used</h2>
          </div>
          <p>Your content is used to retrieve relevant passages and generate answers grounded in those sources.</p>
          <ul>
            <li>No advertising, resale, or profile building.</li>
            <li>Requests go only to the configured retrieval and model services.</li>
            <li>Usage state supports limits, deletion, and product operation.</li>
          </ul>
        </section>

        <section className="legal-section">
          <div className="legal-section-heading">
            <span className="legal-section-index">03</span>
            <span className="legal-section-icon"><Timer size={18} aria-hidden="true" /></span>
            <h2>Retention and deletion</h2>
          </div>
          <p>Uploaded documents are temporary and scheduled for removal after 24 hours.</p>
          <ul>
            <li>Cleanup runs approximately hourly.</li>
            <li>Individual resources and conversations can be deleted sooner.</li>
            <li>Reset clears session history and uploaded documents.</li>
          </ul>
        </section>

        <section className="legal-section">
          <div className="legal-section-heading">
            <span className="legal-section-index">04</span>
            <span className="legal-section-icon"><KeyRound size={18} aria-hidden="true" /></span>
            <h2>Your API key</h2>
          </div>
          <p>BYOK credentials stay in your browser session and authorize your selected provider.</p>
          <ul>
            <li>DocLens does not persist keys as permanent database records.</li>
            <li>Your provider’s billing and access policies still apply.</li>
            <li>Reset clears the key from the browser session.</li>
          </ul>
        </section>
      </div>
    </div>
  )
}

export default PrivacyPage
