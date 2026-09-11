import { Hash, Tags } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../components/Feedback'
import { api } from '../lib/api'

interface Tag { name: string; count: number }

export function TagsPage() {
  const [tags, setTags] = useState<Tag[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const load = () => { setLoading(true); api<{ items: Tag[] }>('/documents/meta/tags/all').then(result => setTags(result.items)).catch(caught => setError(caught.message)).finally(() => setLoading(false)) }
  useEffect(load, [])
  return <><PageHeader eyebrow="CLASIFICACIÓN TRANSVERSAL" title="Etiquetas" description="Una segunda forma de descubrir contenido sin modificar su posición en el árbol." />{error ? <ErrorState message={error} retry={load} /> : loading ? <LoadingState /> : tags.length ? <div className="tag-grid">{tags.map(tag => <Link to={`/search?q=${encodeURIComponent(tag.name)}`} className="tag-card" key={tag.name}><span className="tag-symbol"><Hash size={20} /></span><div><strong>{tag.name}</strong><span>{tag.count} {tag.count === 1 ? 'documento' : 'documentos'}</span></div></Link>)}</div> : <EmptyState icon={<Tags size={38} />} title="Todavía no hay etiquetas" description="Añade etiquetas desde el editor de documentos para relacionar contenido de distintas bibliotecas." />}</>
}
