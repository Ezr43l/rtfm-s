import { X } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'

export function Modal({ title, description, children, onClose, size = 'medium' }: {
  title: string
  description?: string
  children: ReactNode
  onClose: () => void
  size?: 'small' | 'medium' | 'large'
}) {
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [onClose])
  return <div className="modal-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <section className={`modal modal-${size}`} role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <header className="modal-header">
        <div><h2 id="modal-title">{title}</h2>{description && <p>{description}</p>}</div>
        <button className="icon-button" onClick={onClose} aria-label="Cerrar"><X size={19} /></button>
      </header>
      {children}
    </section>
  </div>
}
