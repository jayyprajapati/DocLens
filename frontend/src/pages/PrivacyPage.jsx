import { Database, LockKeyhole, ShieldCheck, Timer, Waypoints } from 'lucide-react'

function PrivacyPage() {
  return (
    <div className="legal-page">
      <div className="legal-shell">
        <header className="legal-header">
          <h1>Privacy Policy</h1>
          <p>How DocLens handles data for document-based Q&A.</p>
        </header>

        <section className="legal-section">
          <h2><Database size={18} aria-hidden="true" /> Data Collection</h2>
          <p>Uploaded documents are stored temporarily to support retrieval and answer generation.</p>
        </section>

        <section className="legal-section">
          <h2><Waypoints size={18} aria-hidden="true" /> Data Usage</h2>
          <p>Data is used only to retrieve relevant context and answer your queries.</p>
        </section>

        <section className="legal-section">
          <h2><Timer size={18} aria-hidden="true" /> Data Retention</h2>
          <p>Uploaded content is automatically deleted after 24 hours by the cleanup workflow.</p>
        </section>

        <section className="legal-section">
          <h2><LockKeyhole size={18} aria-hidden="true" /> BYOK</h2>
          <p>API keys are used for request authorization and are not stored permanently by backend data stores.</p>
        </section>

        <section className="legal-section">
          <h2><ShieldCheck size={18} aria-hidden="true" /> Security</h2>
          <p>DocLens applies standard transport and service safeguards to protect in-transit data and operational access.</p>
        </section>
      </div>
    </div>
  )
}

export default PrivacyPage
