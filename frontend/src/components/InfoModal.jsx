import { useEffect } from 'react'
import { AnimatePresence, motion as Motion } from 'framer-motion'
import { X } from 'lucide-react'

function InfoModal({ isOpen, onClose, title, children, footer = null }) {
  useEffect(() => {
    if (!isOpen) return
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [isOpen, onClose])

  return (
    <AnimatePresence>
      {isOpen && (
        <Motion.div
          className="modal-overlay"
          onClick={onClose}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          <Motion.div
            className="modal-box"
            role="dialog"
            aria-modal="true"
            aria-label={title}
            onClick={(e) => e.stopPropagation()}
            initial={{ y: 10, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 8, opacity: 0 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
          >
            <div className="modal-header">
              <h2 className="modal-title">{title}</h2>
              <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
                <X size={15} />
              </button>
            </div>

            <div className="modal-body">{children}</div>

            {(footer || onClose) && (
              <div className="modal-footer">
                {footer}
                <button type="button" className="button" onClick={onClose}>Close</button>
              </div>
            )}
          </Motion.div>
        </Motion.div>
      )}
    </AnimatePresence>
  )
}

export default InfoModal
