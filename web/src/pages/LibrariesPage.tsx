import { ArrowRight, BookOpen, FolderTree, Library, Pencil, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../components/Feedback'
import { LibraryDialog } from '../components/LibraryDialog'
import { useAuth } from '../context/AuthContext'
import { api } from '../lib/api'
import { canOperate } from '../lib/permissions'
import type { Library as LibraryType } from '../types'

export function LibrariesPage() {
  const { session } = useAuth()
  const canCreate = canOperate(session?.role)
  const [libraries, setLibraries] = useState<LibraryType[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [dialog, setDialog] = useState<LibraryType | 'create' | null>(null)
  const load = () => {
    setLoading(true); setError('')
    api<{ items: LibraryType[] }>('/libraries').then(result => setLibraries(result.items)).catch(caught => setError(caught.message)).finally(() => setLoading(false))
  }
  useEffect(load, [])
  return <>
    <PageHeader eyebrow="DOCUMENTACIÓN" title="Bibliotecas" description="Cada biblioteca contiene su propio árbol libre de categorías y documentos." actions={canCreate && <button className="button primary" onClick={() => setDialog('create')}><Plus size={18} /> Nueva biblioteca</button>} />
    {error ? <ErrorState message={error} retry={load} /> : loading ? <LoadingState /> : libraries.length ? <div className="library-grid">{libraries.map(library => <article className={`library-card accent-${library.color}`} key={library.id}>
      <Link className="library-card-link" to={`/libraries/${library.id}`}>
        <div className="library-icon"><Library size={25} /></div>
        <div className="library-title"><h2>{library.name}</h2><ArrowRight size={19} /></div>
        <p>{library.description || 'Biblioteca documental sin descripción.'}</p>
        <div className="library-counts"><span><FolderTree size={16} /> {library.counts?.categories || 0} categorías</span><span><BookOpen size={16} /> {library.counts?.documents || 0} documentos</span></div>
      </Link>
      {canOperate(library.effective_role) && <button className="library-edit-button" onClick={() => setDialog(library)} title={`Editar ${library.name}`} aria-label={`Editar biblioteca ${library.name}`}><Pencil size={16} /></button>}
    </article>)}</div> : <EmptyState icon={<Library size={38} />} title={canCreate ? 'Crea tu primera biblioteca' : 'No hay bibliotecas disponibles'} description="Las bibliotecas son los espacios raíz. Dentro podrás crear categorías, subcategorías y documentos sin una estructura impuesta." action={canCreate && <button className="button primary" onClick={() => setDialog('create')}><Plus size={18} /> Crear biblioteca</button>} />}
    {dialog && (dialog === 'create' ? canCreate : canOperate(dialog.effective_role)) && <LibraryDialog library={dialog === 'create' ? undefined : dialog} onClose={() => setDialog(null)} onSaved={() => { setDialog(null); load() }} />}
  </>
}
