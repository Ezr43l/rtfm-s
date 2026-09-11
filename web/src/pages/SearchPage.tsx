import { FileSearch, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { DocumentTable } from '../components/DocumentTable'
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../components/Feedback'
import { api } from '../lib/api'
import type { DocumentMeta } from '../types'

export function SearchPage() {
  const [params, setParams] = useSearchParams()
  const query = params.get('q') || ''
  const [draft, setDraft] = useState(query)
  const [documents, setDocuments] = useState<DocumentMeta[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    setDraft(query)
    if (!query) { setDocuments([]); return }
    setLoading(true); setError('')
    api<{ items: DocumentMeta[] }>(`/documents?query=${encodeURIComponent(query)}`).then(result => setDocuments(result.items)).catch(caught => setError(caught.message)).finally(() => setLoading(false))
  }, [query])
  const submit = (event: React.FormEvent) => { event.preventDefault(); setParams(draft.trim() ? { q: draft.trim() } : {}) }
  return <><PageHeader eyebrow="BÚSQUEDA GLOBAL" title="Buscar documentación" description="Localiza documentos por título, resumen o etiqueta." />
    <form className="search-page-form" onSubmit={submit}><Search size={20} /><input autoFocus value={draft} onChange={event => setDraft(event.target.value)} placeholder="¿Qué necesitas encontrar?" /><button className="button primary">Buscar</button></form>
    {error ? <ErrorState message={error} /> : loading ? <LoadingState label="Buscando…" /> : query && documents.length ? <><p className="result-count">{documents.length} resultados para <strong>«{query}»</strong></p><DocumentTable documents={documents} /></> : <EmptyState icon={<FileSearch size={38} />} title={query ? 'No hay coincidencias' : 'Busca en toda la base documental'} description={query ? 'Prueba con un término más general o con una etiqueta.' : 'Los resultados respetarán la estructura y los permisos del contenido.'} />}
  </>
}
