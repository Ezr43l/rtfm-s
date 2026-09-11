import { AlertCircle, Inbox, LoaderCircle } from 'lucide-react'
import type { ReactNode } from 'react'

export function LoadingState({ label = 'Cargando…' }: { label?: string }) {
  return <div className="state-block"><LoaderCircle className="spin" size={24} /><span>{label}</span></div>
}

export function EmptyState({ title, description, action, icon }: { title: string; description: string; action?: ReactNode; icon?: ReactNode }) {
  return <div className="empty-state">{icon || <Inbox size={34} />}<h3>{title}</h3><p>{description}</p>{action}</div>
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="error-state"><AlertCircle size={22} /><div><strong>No se pudo completar la operación</strong><p>{message}</p></div>{retry && <button className="button secondary" onClick={retry}>Reintentar</button>}</div>
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return <header className="page-header"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1>{description && <p>{description}</p>}</div>{actions && <div className="page-actions">{actions}</div>}</header>
}
