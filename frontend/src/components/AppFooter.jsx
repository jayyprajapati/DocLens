import { ExternalLink } from 'lucide-react'
import { Link } from 'react-router-dom'

const PORTFOLIO_URL = 'https://github.com/jayyprajapati'

function AppFooter() {
  const currentYear = new Date().getFullYear()

  return (
    <footer className="app-footer" aria-label="DocLens footer">
      <div className="footer-left">© {currentYear} DocLens. All rights reserved.</div>
      <div className="footer-center">The response is AI-generated. Verify sources.</div>
      <div className="footer-right">
        <Link className="footer-link" to="/privacy">Privacy Policy</Link>
        <span className="footer-dot" aria-hidden="true">•</span>
        <Link className="footer-link" to="/terms">Terms of Use</Link>
        <span className="footer-dot" aria-hidden="true">•</span>
        <a
          className="footer-link footer-link-external"
          href={PORTFOLIO_URL}
          target="_blank"
          rel="noreferrer noopener"
        >
          <span>Portfolio</span>
          <ExternalLink size={13} aria-hidden="true" />
        </a>
      </div>
    </footer>
  )
}

export default AppFooter
