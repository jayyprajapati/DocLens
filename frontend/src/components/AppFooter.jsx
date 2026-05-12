function AppFooter() {
  return (
    <footer className="app-footer" aria-label="DocLens footer">
      <div className="footer-left">© {new Date().getFullYear()} DocLens. All rights reserved.</div>
      <div className="footer-center">The response is AI-generated. Verify sources.</div>
    </footer>
  )
}

export default AppFooter
