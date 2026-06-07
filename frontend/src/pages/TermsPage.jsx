import { AlertTriangle, ArrowLeft, Gauge, KeyRound, ShieldAlert } from 'lucide-react'
import { Link } from 'react-router-dom'

function TermsPage() {
  return (
    <div className="legal-page">
      <div className="legal-shell">
        <header className="legal-header">
          <div className="legal-header-topline">
            <p className="legal-kicker">Terms of use</p>
            <Link className="legal-back-link" to="/">
              <ArrowLeft size={16} aria-hidden="true" />
              <span>Back to DocLens</span>
            </Link>
          </div>
          <h1>
            <span className="legal-title-line">Use the evidence.</span>
            <span className="legal-title-highlight">Keep your judgment.</span>
          </h1>
          <p className="legal-intro">
            These terms set the practical boundaries for using DocLens, including usage limits,
            provider responsibilities, answer verification, and fair use.
          </p>
          <p className="legal-meta">Last updated · March 2026</p>
        </header>

        <div className="legal-summary" aria-label="Terms summary">
          <div className="legal-summary-item">
            <span className="legal-summary-icon"><AlertTriangle size={18} aria-hidden="true" /></span>
            <div className="legal-summary-copy">
              <span className="legal-summary-value">Cited, not guaranteed</span>
              <span className="legal-summary-label">Grounded answers still require your review.</span>
            </div>
          </div>
          <div className="legal-summary-item">
            <span className="legal-summary-icon"><KeyRound size={18} aria-hidden="true" /></span>
            <div className="legal-summary-copy">
              <span className="legal-summary-value">Your provider, your bill</span>
              <span className="legal-summary-label">BYOK usage follows your provider account and limits.</span>
            </div>
          </div>
          <div className="legal-summary-item">
            <span className="legal-summary-icon"><ShieldAlert size={18} aria-hidden="true" /></span>
            <div className="legal-summary-copy">
              <span className="legal-summary-value">Use it fairly</span>
              <span className="legal-summary-label">Responsible use keeps the workspace reliable.</span>
            </div>
          </div>
        </div>

        <section className="legal-section">
          <div className="legal-section-heading">
            <span className="legal-section-index">01</span>
            <span className="legal-section-icon"><Gauge size={18} aria-hidden="true" /></span>
            <h2>Usage limits</h2>
          </div>
          <p>Product limits keep the service reliable and may change over time.</p>
          <ul>
            <li>Free mode: up to 1 document and 2 queries.</li>
            <li>BYOK mode: up to 5 documents and unlimited queries.</li>
            <li>Current limits are surfaced in the product experience.</li>
          </ul>
        </section>

        <section className="legal-section">
          <div className="legal-section-heading">
            <span className="legal-section-index">02</span>
            <span className="legal-section-icon"><KeyRound size={18} aria-hidden="true" /></span>
            <h2>Your API key</h2>
          </div>
          <p>You are responsible for provider access, billing, and protecting your credentials.</p>
          <ul>
            <li>Use only API keys you are authorized to use.</li>
            <li>Never expose keys in screenshots or repositories.</li>
            <li>Provider quotas, policies, and charges remain your responsibility.</li>
          </ul>
        </section>

        <section className="legal-section">
          <div className="legal-section-heading">
            <span className="legal-section-index">03</span>
            <span className="legal-section-icon"><AlertTriangle size={18} aria-hidden="true" /></span>
            <h2>No guarantees</h2>
          </div>
          <p>AI-generated answers and citations can still be incomplete or incorrect.</p>
          <ul>
            <li>Verify important decisions independently.</li>
            <li>Availability depends on upstream providers.</li>
            <li>Source grounding improves traceability, not certainty.</li>
          </ul>
        </section>

        <section className="legal-section">
          <div className="legal-section-heading">
            <span className="legal-section-index">04</span>
            <span className="legal-section-icon"><ShieldAlert size={18} aria-hidden="true" /></span>
            <h2>Fair usage</h2>
          </div>
          <p>Use DocLens lawfully and do not disrupt the service or bypass its controls.</p>
          <ul>
            <li>Do not upload unlawful or malicious content.</li>
            <li>Do not bypass limits, deletion rules, or safety controls.</li>
            <li>Continued use accepts future service updates.</li>
          </ul>
        </section>
      </div>
    </div>
  )
}

export default TermsPage
