import { AlertTriangle, ArrowLeft, Gauge, Handshake, RefreshCcw, ShieldAlert } from 'lucide-react'
import { Link } from 'react-router-dom'

function TermsPage() {
  return (
    <div className="legal-page">
      <div className="legal-shell">
        <header className="legal-header">
          <h1>Terms of Use</h1>
          <p>
            These terms govern use of the DocLens interface, backend API gateway, and document Q&A workflows.
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
          <h2><Gauge size={18} aria-hidden="true" /> Usage Limits</h2>
          <p>
            Usage limits are enforced by product policy and surfaced in the Usage panel.
          </p>
          <ul>
            <li>Free mode: up to 1 document and 2 queries.</li>
            <li>BYOK mode: up to 5 documents and unlimited queries.</li>
            <li>Limits can change as product policy evolves.</li>
          </ul>
        </section>

        <section className="legal-section">
          <h2><ShieldAlert size={18} aria-hidden="true" /> BYOK Responsibility</h2>
          <p>
            When BYOK is enabled, you are responsible for your key management, account billing, and model selection.
          </p>
          <ul>
            <li>Use only API keys you are authorized to use.</li>
            <li>Do not share exposed keys in screenshots, logs, or public repositories.</li>
            <li>Provider-side billing, quotas, and policy compliance remain your responsibility.</li>
          </ul>
        </section>

        <section className="legal-section">
          <h2><AlertTriangle size={18} aria-hidden="true" /> No Guarantees</h2>
          <p>
            DocLens provides AI-assisted outputs and retrieval references, but responses may still contain
            inaccuracies, omissions, or outdated information.
          </p>
          <ul>
            <li>Always validate important legal, medical, financial, or operational decisions independently.</li>
            <li>Source grounding improves reliability but does not guarantee correctness.</li>
            <li>Service availability and response quality may vary with upstream provider behavior.</li>
          </ul>
        </section>

        <section className="legal-section">
          <h2><Handshake size={18} aria-hidden="true" /> Fair Usage</h2>
          <p>
            You agree not to abuse or disrupt DocLens, its backend endpoints, or integrated infrastructure.
          </p>
          <ul>
            <li>Do not attempt to bypass usage limits, safety constraints, or deletion policies.</li>
            <li>Do not upload unlawful or malicious content intended to compromise systems.</li>
            <li>Do not reverse engineer or misuse service internals beyond documented behavior.</li>
          </ul>
        </section>

        <section className="legal-section">
          <h2><RefreshCcw size={18} aria-hidden="true" /> Changes to Service</h2>
          <p>
            DocLens is actively developed. Features, API routes, model defaults, and usage policies may be
            updated without prior notice to support quality, security, and roadmap changes.
          </p>
          <ul>
            <li>Current backend endpoint set includes query, ingest, generate, delete, and delete-all flows.</li>
            <li>Configuration may depend on environment variables such as base URL and default model settings.</li>
            <li>Continued use after updates constitutes acceptance of revised terms.</li>
          </ul>
        </section>
      </div>
    </div>
  )
}

export default TermsPage
