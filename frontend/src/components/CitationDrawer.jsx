import { X } from 'lucide-react'

const MAX_SNIPPET = 600

function truncate(text, max) {
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

export default function CitationDrawer({ citation, onClose }) {
  if (!citation) return null

  const { index, section, page, text } = citation

  return (
    <div className="cit-drawer" role="dialog" aria-label={`Source ${index}`}>
      <div className="cit-drawer-header">
        <span className="cit-drawer-title">
          Source {index}
          {section && <span className="cit-drawer-section"> · {section}</span>}
          {page != null && <span className="cit-drawer-page"> · p.{page}</span>}
        </span>
        <button
          type="button"
          className="cit-drawer-close"
          onClick={onClose}
          aria-label="Close source"
        >
          <X size={13} />
        </button>
      </div>
      <p className="cit-drawer-text">{truncate(text, MAX_SNIPPET)}</p>
    </div>
  )
}
