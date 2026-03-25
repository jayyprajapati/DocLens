import { AlertTriangle, Gauge, Handshake, RefreshCcw, ShieldAlert } from 'lucide-react'

function TermsPage() {
  return (
    <div className="legal-page">
      <div className="legal-shell">
        <header className="legal-header">
          <h1>Terms of Use</h1>
          <p>Usage expectations and responsibilities for using DocLens.</p>
        </header>

        <section className="legal-section">
          <h2><Gauge size={18} aria-hidden="true" /> Usage Limits</h2>
          <p>Free and BYOK tiers follow quota limits shown in the application usage panel.</p>
        </section>

        <section className="legal-section">
          <h2><ShieldAlert size={18} aria-hidden="true" /> BYOK Responsibility</h2>
          <p>You are responsible for providing a valid API key and model selection when BYOK is enabled.</p>
        </section>

        <section className="legal-section">
          <h2><AlertTriangle size={18} aria-hidden="true" /> No Guarantees</h2>
          <p>AI outputs can be incomplete or incorrect; always verify important claims and cited sources.</p>
        </section>

        <section className="legal-section">
          <h2><Handshake size={18} aria-hidden="true" /> Fair Usage</h2>
          <p>Do not misuse the platform or attempt to bypass quota, safety, or service restrictions.</p>
        </section>

        <section className="legal-section">
          <h2><RefreshCcw size={18} aria-hidden="true" /> Changes to Service</h2>
          <p>Features and limits may change over time as the product and infrastructure evolve.</p>
        </section>
      </div>
    </div>
  )
}

export default TermsPage
