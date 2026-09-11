import { Archive, RotateCcw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { DocumentTable } from '../components/DocumentTable'
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../components/Feedback'
import { api } from '../lib/api'
import { canOperate } from '../lib/permissions'
import type { DocumentMeta } from '../types'

export function ArchivePage() {
  const [documents, setDocuments] = useState<DocumentMeta[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const load = () => { setLoading(true); api<{ items: DocumentMeta[] }>('/documents?status=archived').then(result => setDocuments(result.items)).catch(caught => setError(caught.message)).finally(() => setLoading(false)) }
  useEffect(load, [])
  const unarchive = async (document: DocumentMeta) => {
    try { await api(`/documents/${document.id}/unarchive`, { method: 'POST' }); load() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo reactivar') }
  }
  return <><PageHeader eyebrow="CONSERVACIÓN" title="Documentos archivados" description="Contenido histórico que se conserva, pero ya no forma parte de la documentación vigente." />{error ? <ErrorState message={error} retry={load} /> : loading ? <LoadingState /> : documents.length ? <DocumentTable documents={documents} action={document => canOperate(document.effective_role) ? <button className="button ghost small" onClick={() => void unarchive(document)}><RotateCcw size={15} /> Reactivar</button> : null} /> : <EmptyState icon={<Archive size={38} />} title="No hay documentos archivados" description="Los documentos antiguos aparecerán aquí sin mezclarse con el conocimiento vigente." />}</>
}
