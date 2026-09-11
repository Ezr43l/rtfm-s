import { RotateCcw, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { DocumentTable } from '../components/DocumentTable'
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../components/Feedback'
import { api } from '../lib/api'
import { hasFullControl } from '../lib/permissions'
import type { DocumentMeta } from '../types'

export function TrashPage() {
  const [documents, setDocuments] = useState<DocumentMeta[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const load = () => { setLoading(true); api<{ items: DocumentMeta[] }>('/documents?include_deleted=true&status=deleted').then(result => setDocuments(result.items)).catch(caught => setError(caught.message)).finally(() => setLoading(false)) }
  useEffect(load, [])
  const restore = async (document: DocumentMeta) => {
    try { await api(`/documents/${document.id}/restore`, { method: 'POST' }); load() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo restaurar') }
  }
  return <><PageHeader eyebrow="RETENCIÓN" title="Papelera" description="Los documentos eliminados permanecen recuperables hasta que expire la retención configurada." />{error ? <ErrorState message={error} retry={load} /> : loading ? <LoadingState /> : documents.length ? <DocumentTable documents={documents} action={document => hasFullControl(document.effective_role) ? <button className="button ghost small" onClick={() => void restore(document)}><RotateCcw size={15} /> Restaurar</button> : null} /> : <EmptyState icon={<Trash2 size={38} />} title="La papelera está vacía" description="No hay documentos pendientes de purga ni restauración." />}</>
}
