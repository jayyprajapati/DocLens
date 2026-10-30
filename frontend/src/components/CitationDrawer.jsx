import { X } from 'lucide-react'

const MAX_SNIPPET = 600

function truncate(text, max) {
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

// Window the passage around the verified evidence quote so the highlighted proof is always
// visible, even in long chunks. Falls back to a plain truncation when the quote isn't found.
function highlight(text, quote, max) {
  if (!text) return null
  const at = quote ? text.toLowerCase().indexOf(quote.trim().toLowerCase()) : -1
  if (at < 0) return truncate(text, max)
  const end = at + quote.trim().length
  const start = Math.max(0, Math.min(at - 120, end + 120 - max))
  const stop = Math.min(text.length, start + max)
  return (
    <>
      {start > 0 && '…'}
      {text.slice(start, at)}
      <mark className="cit-quote">{text.slice(at, end)}</mark>
      {text.slice(end, stop)}
      {stop < text.length && '…'}
    </>
  )
}

export default function CitationDrawer({ citation, onClose }) {
  if (!citation) return null

  const { index, section, page, text, quote } = citation

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
      <p className="cit-drawer-text">{highlight(text, quote, MAX_SNIPPET)}</p>
    </div>
  )
}
