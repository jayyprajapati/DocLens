import { Link } from 'react-router-dom'

function AppFooter() {
  return (
    <footer className="app-footer" aria-label="DocLens footer">
      <span>© {new Date().getFullYear()} DocLens</span>
      <span className="footer-dot">·</span>
      <span>AI-generated — verify before relying on any response.</span>
      <span className="footer-dot">·</span>
      <Link className="footer-link" to="/privacy">Privacy</Link>
      <span className="footer-dot">·</span>
      <Link className="footer-link" to="/terms">Terms</Link>
    </footer>
  )
}

export default AppFooter
