import { BookOpen, ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { FavoriteButton } from './FavoriteButton'
import { formatDate } from '../lib/api'
import type { DocumentMeta } from '../types'

export function DocumentTable({ documents, action }: { documents: DocumentMeta[]; action?: (document: DocumentMeta) => React.ReactNode }) {
  return <div className="document-table">
    <div className="document-table-head"><span>Documento</span><span>Estado</span><span>Último cambio</span><span>Autor</span><span /></div>
    {documents.map(document => <div className="document-table-row" key={document.id}>
      <Link className="table-document" to={`/documents/${document.id}`}><span className="document-glyph"><BookOpen size={17} /></span><span><strong>{document.title}</strong><small>{document.summary || 'Sin descripción'}</small></span></Link>
      <span><span className={`status-badge ${document.status}`}>{document.status}</span></span>
      <time>{formatDate(document.updated_at)}</time><span>{document.updated_by}</span>
      <span className="table-action"><FavoriteButton document={document} />{action ? action(document) : <Link className="icon-button" to={`/documents/${document.id}`}><ChevronRight size={17} /></Link>}</span>
    </div>)}
  </div>
}
