import {
  ArrowDown, ArrowUp, BookOpen, ChevronDown, ChevronRight, FilePlus2, Folder, FolderOpen, FolderPlus,
  GripVertical, ListOrdered, Pencil, Plus, ShieldCheck, Trash2,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../components/Feedback'
import { FavoriteButton } from '../components/FavoriteButton'
import { LibraryDialog } from '../components/LibraryDialog'
import { LibraryPermissionsDialog } from '../components/LibraryPermissionsDialog'
import { Modal } from '../components/Modal'
import { useAuth } from '../context/AuthContext'
import { api, jsonBody } from '../lib/api'
import { canOperate, hasFullControl } from '../lib/permissions'
import type { Category, DocumentMeta, DocumentRecord, LibraryTree } from '../types'

function findCategory(categories: Category[], id: string): Category | null {
  for (const category of categories) {
    if (category.id === id) return category
    const nested = findCategory(category.children, id)
    if (nested) return nested
  }
  return null
}

function flattenCategories(categories: Category[], depth = 0): { category: Category; depth: number }[] {
  return categories.flatMap(category => [{ category, depth }, ...flattenCategories(category.children, depth + 1)])
}

function categoryBranchIds(category?: Category): Set<string> {
  if (!category) return new Set()
  return new Set([category.id, ...category.children.flatMap(child => [...categoryBranchIds(child)])])
}

function categoryContains(category: Category, categoryId: string | null): boolean {
  if (!categoryId) return false
  return category.id === categoryId || category.children.some(child => categoryContains(child, categoryId))
}

function findCategoryPath(categories: Category[], categoryId: string, ancestors: Category[] = []): Category[] {
  for (const category of categories) {
    const branch = [...ancestors, category]
    if (category.id === categoryId) return branch
    const nested = findCategoryPath(category.children, categoryId, branch)
    if (nested.length) return nested
  }
  return []
}

function libraryPath(libraryId: string, categoryId: string | null): string {
  return `/libraries/${libraryId}${categoryId ? `?category=${encodeURIComponent(categoryId)}` : ''}`
}

export function LibraryPage() {
  const { session } = useAuth()
  const canManagePermissions = session?.identity_type === 'person' && hasFullControl(session.role)
  const { libraryId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = searchParams.get('category')
  const [tree, setTree] = useState<LibraryTree | null>(null)
  const canEdit = canOperate(tree?.library.effective_role)
  const canDelete = hasFullControl(tree?.library.effective_role)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [categoryDialog, setCategoryDialog] = useState<{ parentId: string | null; edit?: Category } | null>(null)
  const [libraryDialog, setLibraryDialog] = useState(false)
  const [permissionsDialog, setPermissionsDialog] = useState(false)
  const [documentDialog, setDocumentDialog] = useState(false)
  const [reordering, setReordering] = useState(false)
  const [draggedCategoryId, setDraggedCategoryId] = useState<string | null>(null)
  const navigate = useNavigate()
  const load = useCallback(() => {
    setLoading(true); setError('')
    api<LibraryTree>(`/libraries/${libraryId}/tree`).then(setTree).catch(caught => setError(caught.message)).finally(() => setLoading(false))
  }, [libraryId])
  useEffect(load, [load])
  const selected = tree && selectedId ? findCategory(tree.categories, selectedId) : null
  const selectedPath = useMemo(() => tree && selectedId ? findCategoryPath(tree.categories, selectedId) : [], [selectedId, tree])
  const levelCategories = selected ? selected.children : tree?.categories || []
  const levelDocuments = selected ? selected.documents : tree?.documents || []
  const sortMode = tree?.library.category_sort || 'manual'
  const currentLibraryPath = libraryPath(libraryId, selectedId)

  const removeCategory = async (category: Category) => {
    if (!window.confirm(`¿Eliminar la categoría vacía «${category.name}»?`)) return
    try {
      await api(`/categories/${category.id}`, { method: 'DELETE' })
      if (selectedId === category.id) setSearchParams({})
      load()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo eliminar') }
  }

  const changeSortMode = async (categorySort: 'manual' | 'alphabetical') => {
    if (!tree || categorySort === sortMode) return
    setReordering(true); setError('')
    try {
      await api(`/libraries/${libraryId}`, { method: 'PATCH', ...jsonBody({ category_sort: categorySort }) })
      load()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo cambiar el orden') }
    finally { setReordering(false) }
  }

  const saveCategoryOrder = async (categories: Category[]) => {
    if (reordering || categories.map(item => item.id).join() === levelCategories.map(item => item.id).join()) return
    setReordering(true); setError('')
    try {
      await api(`/libraries/${libraryId}/categories/order`, {
        method: 'PUT',
        ...jsonBody({ parent_id: selected?.id || null, category_ids: categories.map(item => item.id) }),
      })
      load()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo guardar el orden manual') }
    finally { setReordering(false); setDraggedCategoryId(null) }
  }

  const moveCategory = (index: number, offset: number) => {
    const destination = index + offset
    if (destination < 0 || destination >= levelCategories.length) return
    const next = [...levelCategories]
    const [moved] = next.splice(index, 1)
    next.splice(destination, 0, moved)
    void saveCategoryOrder(next)
  }

  const dropCategory = (targetId: string) => {
    if (!draggedCategoryId || draggedCategoryId === targetId) return setDraggedCategoryId(null)
    const next = [...levelCategories]
    const sourceIndex = next.findIndex(item => item.id === draggedCategoryId)
    const originalTargetIndex = next.findIndex(item => item.id === targetId)
    if (sourceIndex < 0) return setDraggedCategoryId(null)
    const [moved] = next.splice(sourceIndex, 1)
    const targetIndex = next.findIndex(item => item.id === targetId)
    next.splice(Math.max(0, targetIndex + (sourceIndex < originalTargetIndex ? 1 : 0)), 0, moved)
    void saveCategoryOrder(next)
  }

  if (error && !tree) return <ErrorState message={error} retry={load} />
  if (loading && !tree) return <LoadingState label="Construyendo el árbol documental…" />
  if (!tree) return null
  return <>
    <PageHeader eyebrow="BIBLIOTECA" title={tree.library.name} description={tree.library.description || 'Organiza aquí categorías, subcategorías y documentos.'} actions={(canEdit || canManagePermissions) && <>{canManagePermissions && <button className="button ghost" onClick={() => setPermissionsDialog(true)}><ShieldCheck size={17} /> Permisos</button>}{canEdit && <><button className="button ghost" onClick={() => setLibraryDialog(true)}><Pencil size={17} /> Editar biblioteca</button><button className="button secondary" onClick={() => setCategoryDialog({ parentId: selected?.id || null })}><FolderPlus size={18} /> Nueva categoría</button><button className="button primary" onClick={() => setDocumentDialog(true)}><FilePlus2 size={18} /> Nuevo documento</button></>}</>} />
    {error && <ErrorState message={error} />}
    <div className="library-workspace">
      <aside className="tree-panel">
        <div className="tree-panel-heading"><span>ESTRUCTURA</span>{canEdit && <button className="icon-button" onClick={() => setCategoryDialog({ parentId: null })} title="Nueva categoría"><Plus size={17} /></button>}</div>
        <button className={`tree-root ${!selectedId ? 'selected' : ''}`} onClick={() => setSearchParams({})}><FolderOpen size={18} /><span>{tree.library.name}</span></button>
        <div className="tree-content">
          {tree.categories.map(category => <TreeCategory key={category.id} category={category} libraryId={libraryId} selectedId={selectedId} onSelect={id => setSearchParams({ category: id })} onOpenDocument={categoryId => setSearchParams(categoryId ? { category: categoryId } : {}, { replace: true })} onAdd={canEdit ? parentId => setCategoryDialog({ parentId }) : undefined} onEdit={canEdit ? edit => setCategoryDialog({ parentId: edit.parent_id, edit }) : undefined} />)}
          {tree.documents.map(document => <TreeDocument key={document.id} document={document} libraryId={libraryId} categoryId={null} onOpen={categoryId => setSearchParams(categoryId ? { category: categoryId } : {}, { replace: true })} />)}
        </div>
      </aside>
      <section className="folder-view">
        <div className="folder-toolbar">
          <LibraryBreadcrumbs libraryName={tree.library.name} categories={selectedPath} onNavigate={categoryId => setSearchParams(categoryId ? { category: categoryId } : {})} />
          <div className="folder-toolbar-tools">
            <label className="category-sort-control"><ListOrdered size={15} /><span>Orden</span><select value={sortMode} onChange={event => void changeSortMode(event.target.value as 'manual' | 'alphabetical')} disabled={!canEdit || reordering} aria-label="Orden de categorías"><option value="manual">Manual</option><option value="alphabetical">Alfabético A–Z</option></select></label>
            {selected && (canEdit || canDelete) && <div className="folder-actions">{canEdit && <button className="button ghost small" onClick={() => setCategoryDialog({ parentId: selected.parent_id, edit: selected })}><Pencil size={15} /> Editar</button>}{canDelete && <button className="button ghost small danger-text" onClick={() => void removeCategory(selected)}><Trash2 size={15} /> Eliminar</button>}</div>}
          </div>
        </div>
        {selected?.description && <p className="selected-category-description">{selected.description}</p>}
        {(levelCategories.length || levelDocuments.length) ? <div className="folder-items">
          {levelCategories.map((category, index) => <div className={`folder-item ${draggedCategoryId === category.id ? 'dragging' : ''}`} key={category.id} draggable={canEdit && sortMode === 'manual' && !reordering} onDragStart={() => setDraggedCategoryId(category.id)} onDragEnd={() => setDraggedCategoryId(null)} onDragOver={event => { if (sortMode === 'manual') event.preventDefault() }} onDrop={() => dropCategory(category.id)}><button className="folder-item-main" onClick={() => setSearchParams({ category: category.id })}><div className="folder-glyph"><Folder size={22} /></div><div><strong>{category.name}</strong><span>{category.description || `${category.children.length} categorías · ${category.documents.length} documentos`}</span>{category.description && <small>{category.children.length} categorías · {category.documents.length} documentos</small>}</div><ChevronRight size={18} /></button>{canEdit && <div className="folder-item-actions">{sortMode === 'manual' && <><GripVertical className="drag-handle" size={16} aria-label="Arrastrar para reordenar" /><button onClick={() => moveCategory(index, -1)} disabled={index === 0 || reordering} title="Subir categoría" aria-label={`Subir ${category.name}`}><ArrowUp size={15} /></button><button onClick={() => moveCategory(index, 1)} disabled={index === levelCategories.length - 1 || reordering} title="Bajar categoría" aria-label={`Bajar ${category.name}`}><ArrowDown size={15} /></button></>}<button onClick={() => setCategoryDialog({ parentId: category.parent_id, edit: category })} title={`Editar ${category.name}`} aria-label={`Editar categoría ${category.name}`}><Pencil size={16} /></button></div>}</div>)}
          {levelDocuments.map(document => <div className="file-item" key={document.id}><Link className="file-item-main" to={`/documents/${document.id}`} state={{ from: currentLibraryPath }}><div className="file-glyph"><BookOpen size={20} /></div><div><strong>{document.title}</strong><span>{document.summary || 'Documento sin descripción'}</span></div><div className="tag-row">{document.tags?.slice(0, 2).map(tag => <span className="tag" key={tag}>{tag}</span>)}</div><ChevronRight size={18} /></Link><FavoriteButton document={document} /></div>)}
        </div> : <EmptyState icon={<FolderOpen size={38} />} title={selected ? 'Esta categoría está vacía' : 'La biblioteca está vacía'} description={canEdit ? 'Crea una categoría para organizar el árbol o añade directamente un documento en este nivel.' : 'No hay contenido disponible en este nivel.'} action={canEdit && <div className="empty-actions"><button className="button secondary" onClick={() => setCategoryDialog({ parentId: selected?.id || null })}><FolderPlus size={17} /> Crear categoría</button><button className="button primary" onClick={() => setDocumentDialog(true)}><FilePlus2 size={17} /> Crear documento</button></div>} />}
      </section>
    </div>
    {canEdit && categoryDialog && <CategoryDialog libraryId={libraryId} tree={tree} parentId={categoryDialog.parentId} edit={categoryDialog.edit} onClose={() => setCategoryDialog(null)} onSaved={() => { setCategoryDialog(null); load() }} />}
    {canEdit && libraryDialog && <LibraryDialog library={tree.library} onClose={() => setLibraryDialog(false)} onSaved={() => { setLibraryDialog(false); load() }} />}
    {canManagePermissions && permissionsDialog && <LibraryPermissionsDialog libraryId={libraryId} onClose={() => setPermissionsDialog(false)} onSaved={() => { setPermissionsDialog(false); load() }} />}
    {canEdit && documentDialog && <DocumentDialog libraryId={libraryId} categoryId={selected?.id || null} onClose={() => setDocumentDialog(false)} onCreated={document => navigate(`/documents/${document.meta.id}/edit`, { state: { from: currentLibraryPath } })} />}
  </>
}

function LibraryBreadcrumbs({ libraryName, categories, onNavigate }: { libraryName: string; categories: Category[]; onNavigate: (categoryId: string | null) => void }) {
  const entries = useMemo(() => [{ id: null, name: libraryName }, ...categories.map(category => ({ id: category.id, name: category.name }))], [categories, libraryName])
  const containerRef = useRef<HTMLDivElement>(null)
  const measureRef = useRef<HTMLDivElement>(null)
  const [visibleStart, setVisibleStart] = useState(0)
  const recalculate = useCallback(() => {
    const container = containerRef.current
    const measure = measureRef.current
    if (!container || !measure || !entries.length || !container.clientWidth) return
    const labels = Array.from(measure.querySelectorAll<HTMLElement>('[data-breadcrumb-label]'))
    const separator = measure.querySelector<HTMLElement>('[data-breadcrumb-separator]')
    const ellipsis = measure.querySelector<HTMLElement>('[data-breadcrumb-ellipsis]')
    if (labels.length !== entries.length || !separator || !ellipsis) return
    const gap = Number.parseFloat(getComputedStyle(container).gap) || 5
    const separatorWidth = separator.getBoundingClientRect().width
    const labelWidths = labels.map(label => label.getBoundingClientRect().width)
    const fullWidth = labelWidths.reduce((total, width) => total + width, 0) + Math.max(0, entries.length - 1) * (separatorWidth + gap * 2)
    if (fullWidth <= container.clientWidth) {
      setVisibleStart(current => current === 0 ? current : 0)
      return
    }
    const ellipsisWidth = ellipsis.getBoundingClientRect().width
    const prefixWidth = ellipsisWidth + separatorWidth + gap * 2
    let start = entries.length - 1
    let suffixWidth = labelWidths[start]
    while (start > 0) {
      const candidate = labelWidths[start - 1] + separatorWidth + gap * 2 + suffixWidth
      if (prefixWidth + candidate > container.clientWidth) break
      start -= 1
      suffixWidth = candidate
    }
    setVisibleStart(current => current === start ? current : start)
  }, [entries])
  useEffect(() => {
    recalculate()
    const container = containerRef.current
    if (!container) return undefined
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', recalculate)
      return () => window.removeEventListener('resize', recalculate)
    }
    const observer = new ResizeObserver(recalculate)
    observer.observe(container)
    return () => observer.disconnect()
  }, [recalculate])
  const isTruncated = visibleStart > 0
  return <div className="breadcrumbs" ref={containerRef} aria-label="Ruta de navegación">
    {isTruncated && <><span className="breadcrumb-ellipsis" data-breadcrumb-ellipsis aria-hidden="true">…</span><ChevronRight size={15} aria-hidden="true" /></>}
    {entries.slice(visibleStart).map((entry, index) => {
      const isCurrent = visibleStart + index === entries.length - 1
      return <span className="breadcrumb-item" key={entry.id || 'library'}>{index > 0 && <ChevronRight size={15} aria-hidden="true" />}{isCurrent ? <strong title={entry.name} aria-current="page">{entry.name}</strong> : <button title={`Ir a ${entry.name}`} onClick={() => onNavigate(entry.id)}>{entry.name}</button>}</span>
    })}
    <div className="breadcrumbs-measure" ref={measureRef} aria-hidden="true">
      <span data-breadcrumb-ellipsis>…</span><ChevronRight data-breadcrumb-separator size={15} />
      {entries.map((entry, index) => <span className="breadcrumb-measure-item" key={entry.id || 'library'}>{index > 0 && <ChevronRight size={15} />}<span data-breadcrumb-label>{entry.name}</span></span>)}
    </div>
  </div>
}

function TreeCategory({ category, libraryId, selectedId, onSelect, onOpenDocument, onAdd, onEdit }: { category: Category; libraryId: string; selectedId: string | null; onSelect: (id: string) => void; onOpenDocument: (categoryId: string | null) => void; onAdd?: (id: string) => void; onEdit?: (category: Category) => void }) {
  const selectedBranch = categoryContains(category, selectedId)
  const [open, setOpen] = useState(selectedBranch)
  const hasChildren = category.children.length > 0 || category.documents.length > 0
  useEffect(() => { if (selectedBranch) setOpen(true) }, [selectedBranch])
  return <div className="tree-node">
    <div className={`tree-node-row ${selectedId === category.id ? 'selected' : ''}`}>
      <button className="tree-toggle" onClick={() => setOpen(value => !value)} disabled={!hasChildren} aria-expanded={hasChildren ? open : undefined} aria-label={hasChildren ? `${open ? 'Contraer' : 'Desplegar'} ${category.name}` : undefined}>{hasChildren ? (open ? <ChevronDown size={15} /> : <ChevronRight size={15} />) : <span />}</button>
      <button className="tree-label" onClick={() => { setOpen(true); onSelect(category.id) }}>{open ? <FolderOpen size={17} /> : <Folder size={17} />}<span>{category.name}</span></button>
      {(onAdd || onEdit) && <span className="tree-node-actions">{onEdit && <button className="tree-edit" onClick={() => onEdit(category)} title="Editar categoría"><Pencil size={13} /></button>}{onAdd && <button className="tree-add" onClick={() => onAdd(category.id)} title="Crear subcategoría"><Plus size={14} /></button>}</span>}
    </div>
    {open && hasChildren && <div className="tree-children">
      {category.children.map(child => <TreeCategory key={child.id} category={child} libraryId={libraryId} selectedId={selectedId} onSelect={onSelect} onOpenDocument={onOpenDocument} onAdd={onAdd} onEdit={onEdit} />)}
      {category.documents.map(document => <TreeDocument key={document.id} document={document} libraryId={libraryId} categoryId={category.id} onOpen={onOpenDocument} />)}
    </div>}
  </div>
}

function TreeDocument({ document, libraryId, categoryId, onOpen }: { document: DocumentMeta; libraryId: string; categoryId: string | null; onOpen: (categoryId: string | null) => void }) {
  const from = libraryPath(libraryId, categoryId)
  return <Link to={`/documents/${document.id}`} state={{ from }} onClick={() => onOpen(categoryId)} className="tree-document" title={document.title}><BookOpen size={15} /><span>{document.title}</span></Link>
}

function CategoryDialog({ libraryId, tree, parentId, edit, onClose, onSaved }: { libraryId: string; tree: LibraryTree; parentId: string | null; edit?: Category; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(edit?.name || '')
  const [description, setDescription] = useState(edit?.description || '')
  const [selectedParent, setSelectedParent] = useState<string>(edit?.parent_id || parentId || '')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const excludedParents = categoryBranchIds(edit)
  const options = flattenCategories(tree.categories).filter(item => !excludedParents.has(item.category.id))
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setSaving(true); setError('')
    try {
      const payload = { name, description, parent_id: selectedParent || null }
      await api(edit ? `/categories/${edit.id}` : `/libraries/${libraryId}/categories`, { method: edit ? 'PATCH' : 'POST', ...jsonBody(payload) })
      onSaved()
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo guardar la categoría') }
    finally { setSaving(false) }
  }
  return <Modal title={edit ? 'Editar categoría' : 'Nueva categoría'} description="Las categorías funcionan como carpetas y pueden contener otras categorías." onClose={onClose}>
    <form className="modal-body form-stack" onSubmit={submit}>
      <label className="field"><span>Nombre</span><input autoFocus value={name} onChange={event => setName(event.target.value)} required /></label>
      <label className="field"><span>Ubicación</span><select value={selectedParent} onChange={event => setSelectedParent(event.target.value)}><option value="">Raíz de {tree.library.name}</option>{options.map(({ category, depth }) => <option value={category.id} key={category.id}>{'— '.repeat(depth + 1)}{category.name}</option>)}</select></label>
      <label className="field"><span>Descripción <small>Opcional</small></span><textarea rows={3} value={description} onChange={event => setDescription(event.target.value)} /></label>
      {error && <div className="form-error">{error}</div>}
      <div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancelar</button><button className="button primary" disabled={saving}>{saving ? 'Guardando…' : 'Guardar categoría'}</button></div>
    </form>
  </Modal>
}

function DocumentDialog({ libraryId, categoryId, onClose, onCreated }: { libraryId: string; categoryId: string | null; onClose: () => void; onCreated: (document: DocumentRecord) => void }) {
  const [title, setTitle] = useState('')
  const [summary, setSummary] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setSaving(true); setError('')
    try {
      const document = await api<DocumentRecord>('/documents', { method: 'POST', ...jsonBody({ library_id: libraryId, category_id: categoryId, title, summary, content: `# ${title}\n\n`, tags: [] }) })
      onCreated(document)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo crear el documento') }
    finally { setSaving(false) }
  }
  return <Modal title="Nuevo documento" description="Se creará en la ubicación que estás viendo." onClose={onClose}>
    <form className="modal-body form-stack" onSubmit={submit}>
      <label className="field"><span>Título</span><input autoFocus value={title} onChange={event => setTitle(event.target.value)} required /></label>
      <label className="field"><span>Descripción breve <small>Opcional</small></span><textarea rows={3} value={summary} onChange={event => setSummary(event.target.value)} /></label>
      {error && <div className="form-error">{error}</div>}
      <div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancelar</button><button className="button primary" disabled={saving}>{saving ? 'Creando…' : 'Crear y editar'}</button></div>
    </form>
  </Modal>
}
