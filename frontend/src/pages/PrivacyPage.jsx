import { ArrowLeft, Database, LockKeyhole, ShieldCheck, Timer, Waypoints } from 'lucide-react'
import { Link } from 'react-router-dom'

function PrivacyPage() {
  return (
    <div className="legal-page">
      <div className="legal-shell">
        <header className="legal-header">
          <h1>Privacy Policy</h1>
          <p>
            This policy explains how DocLens processes data across the React frontend, the FastAPI backend,
            and the upstream retrieval service used for document grounded answers.
          </p>
          <p className="legal-meta">Last updated: March 2026</p>
        </header>

        <div className="legal-back-row">
          <Link className="legal-back-link" to="/">
            <ArrowLeft size={16} aria-hidden="true" />
            <span>Go Back to DocLens</span>
          </Link>
        </div>

        <section className="legal-section">
          <h2><Database size={18} aria-hidden="true" /> Data Collection</h2>
          <p>
            DocLens collects the minimum information needed to run document Q&A:
          </p>
          <ul>
            <li>Uploaded files for ingestion and retrieval, including PDF, DOCX/DOC, and Markdown content.</li>
            <li>Session identifiers used to separate document scope between users in active sessions.</li>
            <li>Question text submitted in the chat interface and system usage counters for limits.</li>
            <li>Optional BYOK configuration provided in the client session (API key and model selection).</li>
          </ul>
        </section>

        <section className="legal-section">
          <h2><Waypoints size={18} aria-hidden="true" /> Data Usage</h2>
          <p>
            Data is used only to operate DocLens features. The frontend calls backend endpoints for
            ingest/query actions, and the backend forwards those requests to the configured retrieval service.
          </p>
          <ul>
            <li>Ingestion uploads a document for indexing and retrieval context.</li>
            <li>Queries run retrieval + generation to produce grounded responses with sources.</li>
            <li>System messages, usage state, and reset actions are used for product operation only.</li>
          </ul>
        </section>

        <section className="legal-section">
          <h2><Timer size={18} aria-hidden="true" /> Data Retention</h2>
          <p>
            Uploaded documents are temporary. DocLens tracks documents in a backend registry and runs an
            hourly cleanup workflow that removes files older than 24 hours.
          </p>
          <ul>
            <li>Automatic expiry target: 24 hours from registration.</li>
            <li>Cleanup cadence: approximately every 60 minutes.</li>
            <li>Manual deletion is also available through reset and delete actions.</li>
          </ul>
        </section>

        <section className="legal-section">
          <h2><LockKeyhole size={18} aria-hidden="true" /> BYOK</h2>
          <p>
            Bring Your Own Key (BYOK) lets you provide an API key and model for your own provider usage.
            BYOK credentials are intended for request authorization and user-controlled model access.
          </p>
          <ul>
            <li>BYOK values are held in client session storage to support ongoing interaction.</li>
            <li>DocLens backend does not persist API keys as permanent database records.</li>
            <li>You are responsible for protecting your own API credentials.</li>
          </ul>
        </section>

        <section className="legal-section">
          <h2><ShieldCheck size={18} aria-hidden="true" /> Security</h2>
          <p>
            DocLens applies standard service safeguards for local development and deployment hygiene,
            including request validation and controlled endpoint behavior.
          </p>
          <ul>
            <li>Backend acts as a gateway layer and normalizes requests before forwarding.</li>
            <li>CORS boundaries are enforced for approved frontend origins.</li>
            <li>You should run DocLens behind secure transport and infrastructure controls in production.</li>
          </ul>
        </section>
      </div>
    </div>
  )
}

export default PrivacyPage
