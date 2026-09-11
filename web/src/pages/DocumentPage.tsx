import { Archive, ArrowLeft, BookOpen, Check, Edit3, Eye, FileDown, FolderInput, RotateCcw, Save, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useMatch, useNavigate, useParams } from 'react-router-dom'
import { ErrorState, LoadingState } from '../components/Feedback'
import { FavoriteButton } from '../components/FavoriteButton'
import { MarkdownEditor } from '../components/MarkdownEditor'
import { MarkdownRenderer } from '../components/MarkdownRenderer'
import { Modal } from '../components/Modal'
import { api, formatDate, jsonBody } from '../lib/api'
import { canOperate, hasFullControl } from '../lib/permissions'
import type { Category, DocumentRecord, Library, LibraryTree } from '../types'

const pause = (milliseconds: number) => new Promise<void>(resolve => window.setTimeout(resolve, milliseconds))

async function preparePrintableDocument(root: HTMLElement) {
  const images = Array.from(root.querySelectorAll('img'))
  images.forEach(image => { image.loading = 'eager' })
  const imageWait = Promise.all(images.map(image => image.complete ? Promise.resolve() : new Promise<void>(resolve => {
    const finish = () => { image.removeEventListener('load', finish); image.removeEventListener('error', finish); resolve() }
    image.addEventListener('load', finish)
    image.addEventListener('error', finish)
  })))
  await Promise.race([imageWait, pause(8_000)])

  const diagramDeadline = Date.now() + 8_000
  while (root.querySelector('.diagram-loading') && Date.now() < diagramDeadline) await pause(100)
  await new Promise<void>(resolve => window.requestAnimationFrame(() => window.requestAnimationFrame(() => resolve())))
}

function printableFilename(title: string) {
  return title.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-|-$/g, '').toLowerCase() || 'documento-rtfm'
}

export function DocumentPage() {
  const { documentId = '' } = useParams()
  const editing = Boolean(useMatch('/documents/:documentId/edit'))
  const [document, setDocument] = useState<DocumentRecord | null>(null)
  const canEdit = canOperate(document?.meta.effective_role)
  const canDelete = hasFullControl(document?.meta.effective_role)
  const [title, setTitle] = useState('')
  const [summary, setSummary] = useState('')
  const [content, setContent] = useState('')
  const [tags, setTags] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [moving, setMoving] = useState(false)
  const [exportingPdf, setExportingPdf] = useState(false)
  const printableRef = useRef<HTMLElement | null>(null)
  const navigate = useNavigate()
  const location = useLocation()
  const dirty = Boolean(document && (
    title !== document.meta.title || summary !== (document.meta.summary || '') ||
    content !== (document.content || '') || tags !== (document.meta.tags || []).join(', ')
  ))

  const load = useCallback(() => {
    setError('')
    api<DocumentRecord>(`/documents/${documentId}`).then(record => {
      setDocument(record); setTitle(record.meta.title); setSummary(record.meta.summary || '')
      setContent(record.content || ''); setTags((record.meta.tags || []).join(', '))
    }).catch(caught => setError(caught.message))
  }, [documentId])
  useEffect(load, [load])
  useEffect(() => {
    if (!editing || !dirty) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, editing])

  const save = async () => {
    setSaving(true); setError('')
    try {
      const updated = await api<DocumentRecord>(`/documents/${documentId}`, { method: 'PATCH', ...jsonBody({ title, summary, content, tags: tags.split(',').map(tag => tag.trim()).filter(Boolean) }) })
      setDocument(updated); navigate(`/documents/${documentId}`, { replace: true, state: location.state })
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo guardar el documento') }
    finally { setSaving(false) }
  }
  const action = async (kind: 'archive' | 'unarchive' | 'delete' | 'restore') => {
    const destructive = kind === 'delete'
    if (destructive && !window.confirm(`¿Enviar «${document?.meta.title}» a la papelera? Podrás restaurarlo durante el periodo de retención.`)) return
    setError('')
    try {
      if (kind === 'delete') await api(`/documents/${documentId}`, { method: 'DELETE' })
      else await api(`/documents/${documentId}/${kind}`, { method: 'POST' })
      navigate(kind === 'delete' ? '/trash' : kind === 'archive' ? '/archive' : `/documents/${documentId}`, { state: location.state })
      if (!['delete', 'archive'].includes(kind)) load()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo completar la operación') }
  }
  const exportPdf = async () => {
    if (!printableRef.current) return
    setExportingPdf(true); setError('')
    const previousTitle = window.document.title
    try {
      await preparePrintableDocument(printableRef.current)
      window.document.title = printableFilename(document?.meta.title || '')
      window.document.documentElement.classList.add('exporting-document-pdf')
      window.print()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'No se pudo preparar el documento para PDF')
    } finally {
      window.document.documentElement.classList.remove('exporting-document-pdf')
      window.document.title = previousTitle
      setExportingPdf(false)
    }
  }
  if (error && !document) return <ErrorState message={error} retry={load} />
  if (!document) return <LoadingState label="Abriendo documento…" />
  if (editing && !canEdit) return <ErrorState message="Tu nivel de acceso permite consultar este documento, pero no editarlo." />
  const fallbackLibraryPath = document.meta.library_id ? `/libraries/${document.meta.library_id}${document.meta.category_id ? `?category=${encodeURIComponent(document.meta.category_id)}` : ''}` : '/libraries'
  const requestedOrigin = (location.state as { from?: unknown } | null)?.from
  const backPath = typeof requestedOrigin === 'string' && requestedOrigin.startsWith('/libraries/') ? requestedOrigin : fallbackLibraryPath

  return <div className={`document-page ${editing ? 'editing' : ''}`}>
    <div className="document-topline">
      <Link className="back-link" to={backPath}><ArrowLeft size={17} /> Volver a la biblioteca</Link>
      <div className="document-actions">
        {document.meta.status !== 'deleted' && <FavoriteButton document={document.meta} showLabel />}
        {!editing && <button className="button ghost" onClick={() => void exportPdf()} disabled={exportingPdf} title="Abre el diálogo del navegador para guardar el documento como PDF"><FileDown size={17} /> {exportingPdf ? 'Preparando PDF…' : 'Exportar PDF'}</button>}
        {canEdit && document.meta.status !== 'deleted' && <button className="button ghost" onClick={() => setMoving(true)}><FolderInput size={17} /> Mover</button>}
        {canEdit && document.meta.status === 'active' && <button className="button ghost" onClick={() => void action('archive')}><Archive size={17} /> Archivar</button>}
        {canEdit && document.meta.status === 'archived' && <button className="button ghost" onClick={() => void action('unarchive')}><RotateCcw size={17} /> Reactivar</button>}
        {canDelete && document.meta.status !== 'deleted' && <button className="button ghost danger-text" onClick={() => void action('delete')}><Trash2 size={17} /> Papelera</button>}
        {canDelete && document.meta.status === 'deleted' && <button className="button primary" onClick={() => void action('restore')}><RotateCcw size={17} /> Restaurar</button>}
        {canEdit && document.meta.status !== 'deleted' && (!editing ? <Link className="button primary" to={`/documents/${documentId}/edit`} state={location.state}><Edit3 size={17} /> Editar</Link> : <>{dirty && <span className="unsaved-badge">Cambios sin guardar</span>}<Link className="button secondary" to={`/documents/${documentId}`} state={location.state} onClick={event => { if (dirty && !window.confirm('Hay cambios sin guardar. ¿Salir del editor y descartarlos?')) event.preventDefault() }}><Eye size={17} /> Vista</Link><button className="button primary" onClick={() => void save()} disabled={saving || !dirty}><Save size={17} /> {saving ? 'Guardando…' : 'Guardar'}</button></>)}
      </div>
    </div>
    {error && <div className="form-error document-error">{error}</div>}
    {editing ? <div className="editor-layout">
      <section className="editor-main">
        <input className="document-title-input" value={title} onChange={event => setTitle(event.target.value)} aria-label="Título" />
        <textarea className="document-summary-input" value={summary} onChange={event => setSummary(event.target.value)} placeholder="Descripción breve del documento…" rows={2} />
        <MarkdownEditor
          value={content}
          onChange={setContent}
          documentId={documentId}
          images={document.images || []}
          onImageUploaded={image => setDocument(current => current ? { ...current, images: [...(current.images || []), image] } : current)}
          onSave={() => { if (!saving && dirty) void save() }}
        />
      </section>
      <aside className="editor-inspector">
        <h3>Detalles</h3>
        <label className="field"><span>Etiquetas</span><input value={tags} onChange={event => setTags(event.target.value)} placeholder="unraid, red, docker" /><small>Separadas por comas</small></label>
        <dl className="inspector-meta"><div><dt>Estado</dt><dd><span className={`status-badge ${document.meta.status}`}>{document.meta.status}</span></dd></div><div><dt>Última edición</dt><dd>{formatDate(document.meta.updated_at)}</dd></div><div><dt>Autor</dt><dd>{document.meta.updated_by}</dd></div><div><dt>Revisión</dt><dd>{document.meta.version.clock}</dd></div></dl>
      </aside>
    </div> : <article className="document-view" ref={printableRef}>
      <header className="document-header"><div className="document-symbol"><BookOpen size={22} /></div><div className="document-heading"><div className="document-meta-line"><span className={`status-badge ${document.meta.status}`}>{document.meta.status}</span><span>Actualizado {formatDate(document.meta.updated_at)}</span><span>por {document.meta.updated_by}</span></div><h1>{document.meta.title}</h1>{document.meta.summary && <p>{document.meta.summary}</p>}<div className="tag-row">{document.meta.tags?.map(tag => <span className="tag" key={tag}>{tag}</span>)}</div></div></header>
      <MarkdownRenderer content={document.content || ''} />
    </article>}
    {canEdit && moving && <MoveDocumentDialog document={document} onClose={() => setMoving(false)} onMoved={() => { setMoving(false); load() }} />}
  </div>
}

function flatten(categories: Category[], depth = 0): { id: string; name: string; depth: number }[] {
  return categories.flatMap(category => [{ id: category.id, name: category.name, depth }, ...flatten(category.children, depth + 1)])
}

function MoveDocumentDialog({ document, onClose, onMoved }: { document: DocumentRecord; onClose: () => void; onMoved: () => void }) {
  const [libraries, setLibraries] = useState<Library[]>([])
  const [libraryId, setLibraryId] = useState(document.meta.library_id || '')
  const [tree, setTree] = useState<LibraryTree | null>(null)
  const [categoryId, setCategoryId] = useState(document.meta.category_id || '')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    api<{ items: Library[] }>('/libraries')
      .then(result => setLibraries(result.items.filter(library => canOperate(library.effective_role))))
      .catch(caught => setError(caught.message))
  }, [])
  useEffect(() => {
    if (!libraryId) return setTree(null)
    api<LibraryTree>(`/libraries/${libraryId}/tree`).then(setTree).catch(caught => setError(caught.message))
  }, [libraryId])
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setSaving(true); setError('')
    try { await api(`/documents/${document.meta.id}/move`, { method: 'POST', ...jsonBody({ library_id: libraryId, category_id: categoryId || null }) }); onMoved() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo mover el documento') }
    finally { setSaving(false) }
  }
  return <Modal title="Mover documento" description="Cambia su biblioteca o carpeta sin romper su identificador ni su historial." onClose={onClose}>
    <form className="modal-body form-stack" onSubmit={submit}>
      <label className="field"><span>Biblioteca</span><select value={libraryId} onChange={event => { setLibraryId(event.target.value); setCategoryId('') }} required><option value="">Selecciona una biblioteca</option>{libraries.map(library => <option value={library.id} key={library.id}>{library.name}</option>)}</select></label>
      <label className="field"><span>Categoría</span><select value={categoryId} onChange={event => setCategoryId(event.target.value)} disabled={!tree}><option value="">Raíz de la biblioteca</option>{tree && flatten(tree.categories).map(category => <option value={category.id} key={category.id}>{'— '.repeat(category.depth + 1)}{category.name}</option>)}</select></label>
      {error && <div className="form-error">{error}</div>}
      <div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancelar</button><button className="button primary" disabled={saving || !libraryId}><Check size={17} /> {saving ? 'Moviendo…' : 'Mover documento'}</button></div>
    </form>
  </Modal>
}
