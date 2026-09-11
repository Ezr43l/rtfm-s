import {
  Bold, Braces, CheckSquare, Code2, Columns2, Eye, FileCode2, Heading1,
  Heading2, Heading3, HelpCircle, ImagePlus, Italic, Link2, List, ListOrdered,
  Maximize2, Minus, PanelLeft, Quote, Strikethrough, Table2, Upload, Workflow, X,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, jsonBody } from '../lib/api'
import { diagramTemplates } from '../lib/diagramTemplates'
import type { DocumentImage, DocumentMeta } from '../types'
import { Modal } from './Modal'
import { MermaidDiagram } from './MermaidDiagram'
import { MarkdownRenderer } from './MarkdownRenderer'
import { Toast, type ToastTone } from './Toast'

type EditorMode = 'write' | 'split' | 'preview'
type Selection = { start: number; end: number }
type Notice = { id: number; tone: ToastTone; message: string }

function ToolbarButton({ label, shortcut, active = false, onClick, children }: {
  label: string
  shortcut?: string
  active?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return <button type="button" className={`editor-tool ${active ? 'active' : ''}`} onClick={onClick} title={`${label}${shortcut ? ` · ${shortcut}` : ''}`} aria-label={label}>{children}</button>
}

function escapeLabel(value: string) {
  return value.replace(/\\/g, '\\\\').replace(/]/g, '\\]')
}

function imageToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('No se pudo leer la imagen'))
    reader.onload = () => {
      const result = String(reader.result || '')
      const separator = result.indexOf(',')
      if (separator < 0) reject(new Error('La imagen no contiene datos válidos'))
      else resolve(result.slice(separator + 1))
    }
    reader.readAsDataURL(file)
  })
}

function findDiagram(value: string, cursor: number): { start: number; end: number; code: string } | null {
  const expression = /```mermaid\s*\n([\s\S]*?)\n```/gi
  for (const match of value.matchAll(expression)) {
    const start = match.index || 0
    const end = start + match[0].length
    if (cursor >= start && cursor <= end) return { start, end, code: match[1] }
  }
  return null
}

export function MarkdownEditor({
  value, onChange, documentId, images, onImageUploaded, onSave,
}: {
  value: string
  onChange: (value: string) => void
  documentId: string
  images: DocumentImage[]
  onImageUploaded: (image: DocumentImage) => void
  onSave: () => void
}) {
  const textarea = useRef<HTMLTextAreaElement>(null)
  const [mode, setMode] = useState<EditorMode>('split')
  const [fullscreen, setFullscreen] = useState(false)
  const [dialog, setDialog] = useState<'link' | 'image' | 'table' | 'diagram' | 'help' | null>(null)
  const [dialogSelection, setDialogSelection] = useState<Selection>({ start: 0, end: 0 })
  const [diagramDraft, setDiagramDraft] = useState<{ code: string; range: Selection; editing: boolean } | null>(null)
  const [uploading, setUploading] = useState(false)
  const [notice, setNotice] = useState<Notice | null>(null)
  const words = useMemo(() => value.trim() ? value.trim().split(/\s+/u).length : 0, [value])
  const lines = useMemo(() => value.split('\n').length, [value])

  useEffect(() => {
    if (!fullscreen) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previous }
  }, [fullscreen])

  const selection = (): Selection => ({
    start: textarea.current?.selectionStart ?? value.length,
    end: textarea.current?.selectionEnd ?? value.length,
  })
  const showNotice = (tone: ToastTone, message: string) => setNotice(current => ({ id: (current?.id || 0) + 1, tone, message }))
  const commit = (next: string, start: number, end = start) => {
    onChange(next)
    window.requestAnimationFrame(() => {
      textarea.current?.focus()
      textarea.current?.setSelectionRange(start, end)
    })
  }
  const replaceRange = (range: Selection, replacement: string, select?: Selection) => {
    const next = value.slice(0, range.start) + replacement + value.slice(range.end)
    const target = select || { start: range.start + replacement.length, end: range.start + replacement.length }
    commit(next, target.start, target.end)
  }
  const wrap = (prefix: string, suffix: string, placeholder: string) => {
    const range = selection()
    const selected = value.slice(range.start, range.end) || placeholder
    const replacement = `${prefix}${selected}${suffix}`
    const contentStart = range.start + prefix.length
    replaceRange(range, replacement, { start: contentStart, end: contentStart + selected.length })
  }
  const prefixLines = (prefix: string | ((index: number) => string), remove: RegExp) => {
    const range = selection()
    const start = value.lastIndexOf('\n', Math.max(0, range.start - 1)) + 1
    const newline = value.indexOf('\n', range.end)
    const end = newline < 0 ? value.length : newline
    const original = value.slice(start, end)
    const replacement = original.split('\n').map((line, index) => `${typeof prefix === 'function' ? prefix(index) : prefix}${line.replace(remove, '')}`).join('\n')
    replaceRange({ start, end }, replacement, { start, end: start + replacement.length })
  }
  const heading = (level: number) => prefixLines(`${'#'.repeat(level)} `, /^#{1,6}\s+/)
  const insertBlock = (block: string) => {
    const range = selection()
    const before = range.start > 0 && value[range.start - 1] !== '\n' ? '\n\n' : ''
    const after = range.end < value.length && value[range.end] !== '\n' ? '\n\n' : ''
    replaceRange(range, `${before}${block}${after}`)
  }
  const openDialog = (kind: 'link' | 'image' | 'table' | 'help') => {
    setDialogSelection(selection()); setDialog(kind)
  }
  const openDiagram = () => {
    const range = selection()
    const existing = findDiagram(value, range.start)
    setDiagramDraft(existing ? { code: existing.code, range: { start: existing.start, end: existing.end }, editing: true } : {
      code: diagramTemplates[0].code,
      range,
      editing: false,
    })
    setDialog('diagram')
  }
  const insertLink = (label: string, url: string) => {
    const text = escapeLabel(label || url)
    replaceRange(dialogSelection, `[${text}](${url})`)
    setDialog(null)
  }
  const insertImage = (image: { url: string; alt: string }) => {
    replaceRange(dialogSelection, `![${escapeLabel(image.alt || 'Imagen')}](${image.url})`)
    setDialog(null)
  }
  const uploadFile = async (file: File): Promise<DocumentImage> => {
    if (!['image/png', 'image/jpeg', 'image/webp', 'image/gif'].includes(file.type)) throw new Error('Utiliza una imagen PNG, JPEG, WebP o GIF')
    const data = await imageToBase64(file)
    const image = await api<DocumentImage>(`/documents/${documentId}/images`, {
      method: 'POST',
      ...jsonBody({ filename: file.name, media_type: file.type, data }),
    })
    onImageUploaded(image)
    return image
  }
  const uploadAtSelection = async (file: File, range: Selection) => {
    setUploading(true)
    try {
      const image = await uploadFile(file)
      const alt = file.name.replace(/\.[^.]+$/, '') || 'Imagen'
      replaceRange(range, `![${escapeLabel(alt)}](${image.url})`)
      showNotice('success', 'Imagen subida e insertada')
    } catch (caught) {
      showNotice('error', caught instanceof Error ? caught.message : 'No se pudo subir la imagen')
    } finally { setUploading(false) }
  }
  const keyboard = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const modifier = event.ctrlKey || event.metaKey
    if (modifier && event.key.toLocaleLowerCase() === 'b') { event.preventDefault(); wrap('**', '**', 'texto en negrita') }
    else if (modifier && event.key.toLocaleLowerCase() === 'i') { event.preventDefault(); wrap('*', '*', 'texto en cursiva') }
    else if (modifier && event.key.toLocaleLowerCase() === 'k') { event.preventDefault(); openDialog('link') }
    else if (modifier && event.key.toLocaleLowerCase() === 's') { event.preventDefault(); onSave() }
    else if (event.key === 'Tab') {
      event.preventDefault()
      const range = selection()
      if (range.start === range.end) replaceRange(range, '  ')
      else prefixLines('  ', /^/)
    }
  }

  return <div className={`advanced-editor ${fullscreen ? 'is-fullscreen' : ''}`}>
    <div className="editor-toolbar" role="toolbar" aria-label="Herramientas de formato Markdown">
      <div className="editor-tool-group">
        <ToolbarButton label="Título 1" onClick={() => heading(1)}><Heading1 size={18} /></ToolbarButton>
        <ToolbarButton label="Título 2" onClick={() => heading(2)}><Heading2 size={18} /></ToolbarButton>
        <ToolbarButton label="Título 3" onClick={() => heading(3)}><Heading3 size={18} /></ToolbarButton>
      </div>
      <div className="editor-tool-group">
        <ToolbarButton label="Negrita" shortcut="Ctrl+B" onClick={() => wrap('**', '**', 'texto en negrita')}><Bold size={18} /></ToolbarButton>
        <ToolbarButton label="Cursiva" shortcut="Ctrl+I" onClick={() => wrap('*', '*', 'texto en cursiva')}><Italic size={18} /></ToolbarButton>
        <ToolbarButton label="Tachado" onClick={() => wrap('~~', '~~', 'texto tachado')}><Strikethrough size={18} /></ToolbarButton>
        <ToolbarButton label="Código en línea" onClick={() => wrap('`', '`', 'código')}><Code2 size={18} /></ToolbarButton>
      </div>
      <div className="editor-tool-group">
        <ToolbarButton label="Lista" onClick={() => prefixLines('- ', /^\s*(?:[-*+]\s+\[[ xX]\]\s+|[-*+]\s+|\d+\.\s+)/)}><List size={18} /></ToolbarButton>
        <ToolbarButton label="Lista numerada" onClick={() => prefixLines(index => `${index + 1}. `, /^\s*(?:[-*+]\s+\[[ xX]\]\s+|[-*+]\s+|\d+\.\s+)/)}><ListOrdered size={18} /></ToolbarButton>
        <ToolbarButton label="Lista de tareas" onClick={() => prefixLines('- [ ] ', /^\s*(?:[-*+]\s+\[[ xX]\]\s+|[-*+]\s+|\d+\.\s+)/)}><CheckSquare size={18} /></ToolbarButton>
        <ToolbarButton label="Cita" onClick={() => prefixLines('> ', /^>\s+/)}><Quote size={18} /></ToolbarButton>
      </div>
      <div className="editor-tool-group">
        <ToolbarButton label="Enlace" shortcut="Ctrl+K" onClick={() => openDialog('link')}><Link2 size={18} /></ToolbarButton>
        <ToolbarButton label="Imagen privada o remota" onClick={() => openDialog('image')}><ImagePlus size={18} /></ToolbarButton>
        <ToolbarButton label="Tabla" onClick={() => openDialog('table')}><Table2 size={18} /></ToolbarButton>
        <ToolbarButton label="Bloque de código" onClick={() => wrap('```\n', '\n```', 'código')}><FileCode2 size={18} /></ToolbarButton>
        <ToolbarButton label="Separador" onClick={() => insertBlock('---')}><Minus size={18} /></ToolbarButton>
      </div>
      <div className="editor-tool-group diagram-tool-group">
        <ToolbarButton label="Crear o editar diagrama" onClick={openDiagram}><Workflow size={19} /></ToolbarButton>
        <span>Diagrama</span>
      </div>
      <div className="editor-tool-group editor-toolbar-end">
        <ToolbarButton label="Ayuda Markdown" onClick={() => openDialog('help')}><HelpCircle size={18} /></ToolbarButton>
        <ToolbarButton label={fullscreen ? 'Salir de pantalla completa' : 'Pantalla completa'} active={fullscreen} onClick={() => setFullscreen(current => !current)}>{fullscreen ? <X size={18} /> : <Maximize2 size={18} />}</ToolbarButton>
      </div>
    </div>
    <div className="editor-view-switcher" role="tablist" aria-label="Modo del editor">
      <button type="button" role="tab" aria-selected={mode === 'write'} className={mode === 'write' ? 'active' : ''} onClick={() => setMode('write')}><PanelLeft size={16} /> Escribir</button>
      <button type="button" role="tab" aria-selected={mode === 'split'} className={mode === 'split' ? 'active' : ''} onClick={() => setMode('split')}><Columns2 size={16} /> Dividido</button>
      <button type="button" role="tab" aria-selected={mode === 'preview'} className={mode === 'preview' ? 'active' : ''} onClick={() => setMode('preview')}><Eye size={16} /> Vista previa</button>
      <span>{uploading ? <><Upload size={14} className="pulse" /> Subiendo imagen…</> : `${words.toLocaleString('es-ES')} palabras · ${lines.toLocaleString('es-ES')} líneas`}</span>
    </div>
    <div className={`markdown-workbench mode-${mode}`}>
      {mode !== 'preview' && <div className="markdown-source-pane">
        <textarea
          ref={textarea}
          className="markdown-editor"
          value={value}
          readOnly={uploading}
          onChange={event => onChange(event.target.value)}
          onKeyDown={keyboard}
          onPaste={event => {
            const file = Array.from(event.clipboardData.files).find(item => item.type.startsWith('image/'))
            if (!file) return
            event.preventDefault()
            void uploadAtSelection(file, selection())
          }}
          onDrop={event => {
            const file = Array.from(event.dataTransfer.files).find(item => item.type.startsWith('image/'))
            if (!file) return
            event.preventDefault()
            void uploadAtSelection(file, selection())
          }}
          placeholder="Empieza a documentar… Usa la barra superior o escribe Markdown directamente."
          spellCheck
          aria-label="Contenido del documento en Markdown"
        />
      </div>}
      {mode !== 'write' && <div className="editor-preview-pane">
        <div className="preview-heading"><Eye size={15} /> VISTA PREVIA EN DIRECTO</div>
        {value.trim() ? <MarkdownRenderer content={value} className="markdown-body editor-markdown-preview" /> : <div className="preview-empty"><Braces size={30} /><strong>El documento está vacío</strong><span>El contenido aparecerá aquí a medida que escribas.</span></div>}
      </div>}
    </div>
    <div className="editor-statusbar"><span>Markdown + GFM</span><span>{value.length.toLocaleString('es-ES')} caracteres</span><span>Ctrl+S para guardar</span></div>

    {dialog === 'link' && <LinkDialog selectedText={value.slice(dialogSelection.start, dialogSelection.end)} onClose={() => setDialog(null)} onInsert={insertLink} />}
    {dialog === 'image' && <ImageDialog selectedText={value.slice(dialogSelection.start, dialogSelection.end)} images={images} uploadFile={uploadFile} onUploaded={image => showNotice('success', `${image.filename} subida`)} onClose={() => setDialog(null)} onInsert={insertImage} />}
    {dialog === 'table' && <TableDialog onClose={() => setDialog(null)} onInsert={table => { replaceRange(dialogSelection, table); setDialog(null) }} />}
    {dialog === 'diagram' && diagramDraft && <DiagramStudio draft={diagramDraft} onClose={() => { setDialog(null); setDiagramDraft(null) }} onInsert={code => {
      const fence = `\`\`\`mermaid\n${code.trim()}\n\`\`\``
      replaceRange(diagramDraft.range, fence)
      setDialog(null); setDiagramDraft(null)
    }} />}
    {dialog === 'help' && <EditorHelp onClose={() => setDialog(null)} />}
    {notice && <Toast key={notice.id} tone={notice.tone} message={notice.message} onDismiss={() => setNotice(null)} />}
  </div>
}

function LinkDialog({ selectedText, onClose, onInsert }: { selectedText: string; onClose: () => void; onInsert: (label: string, url: string) => void }) {
  const [tab, setTab] = useState<'external' | 'internal'>('external')
  const [label, setLabel] = useState(selectedText)
  const [url, setUrl] = useState('')
  const [query, setQuery] = useState('')
  const [documents, setDocuments] = useState<DocumentMeta[]>([])
  const [error, setError] = useState('')
  useEffect(() => { api<{ items: DocumentMeta[] }>('/documents').then(result => setDocuments(result.items)).catch(() => undefined) }, [])
  const matches = documents.filter(document => `${document.title} ${document.summary}`.toLocaleLowerCase('es-ES').includes(query.toLocaleLowerCase('es-ES'))).slice(0, 8)
  const submit = (event: React.FormEvent) => {
    event.preventDefault(); setError('')
    if (!/^(https?:\/\/|mailto:|\/|#)/i.test(url)) return setError('Utiliza una URL HTTP(S), mailto, una ruta interna o un ancla')
    onInsert(label || url, url)
  }
  return <Modal title="Insertar enlace" description="Enlaza una dirección externa, un ancla o cualquier documento de la base." onClose={onClose} size="large">
    <div className="modal-body form-stack">
      <div className="dialog-tabs"><button type="button" className={tab === 'external' ? 'active' : ''} onClick={() => setTab('external')}><Link2 size={16} /> Dirección</button><button type="button" className={tab === 'internal' ? 'active' : ''} onClick={() => setTab('internal')}><FileCode2 size={16} /> Documento interno</button></div>
      {tab === 'external' ? <form className="form-stack" onSubmit={submit}>
        <label className="field"><span>Texto visible</span><input autoFocus value={label} onChange={event => setLabel(event.target.value)} placeholder="Documentación oficial" /></label>
        <label className="field"><span>Dirección</span><input value={url} onChange={event => setUrl(event.target.value)} placeholder="https://… o #seccion" required /></label>
        {error && <div className="form-error">{error}</div>}
        <div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancelar</button><button className="button primary">Insertar enlace</button></div>
      </form> : <>
        <label className="field"><span>Buscar documento</span><input autoFocus value={query} onChange={event => setQuery(event.target.value)} placeholder="Nombre o descripción…" /></label>
        <div className="internal-document-list">{matches.length ? matches.map(document => <button type="button" key={document.id} onClick={() => onInsert(selectedText || document.title, `/documents/${document.id}`)}><FileCode2 size={18} /><span><strong>{document.title}</strong><small>{document.summary || 'Sin descripción'}</small></span></button>) : <div className="dialog-empty">No hay documentos que coincidan.</div>}</div>
        <div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancelar</button></div>
      </>}
    </div>
  </Modal>
}

function ImageDialog({ selectedText, images, uploadFile, onUploaded, onClose, onInsert }: {
  selectedText: string
  images: DocumentImage[]
  uploadFile: (file: File) => Promise<DocumentImage>
  onUploaded: (image: DocumentImage) => void
  onClose: () => void
  onInsert: (image: { url: string; alt: string }) => void
}) {
  const [tab, setTab] = useState<'upload' | 'library' | 'url'>('upload')
  const [file, setFile] = useState<File | null>(null)
  const [alt, setAlt] = useState(selectedText)
  const [url, setUrl] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const chooseFile = (selected: File | null) => {
    setFile(selected)
    if (selected && !alt) setAlt(selected.name.replace(/\.[^.]+$/, ''))
  }
  const submitFile = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!file) return setError('Selecciona una imagen')
    setSaving(true); setError('')
    try {
      const image = await uploadFile(file)
      onUploaded(image)
      onInsert({ url: image.url, alt: alt || file.name.replace(/\.[^.]+$/, '') })
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo subir la imagen') }
    finally { setSaving(false) }
  }
  const submitUrl = (event: React.FormEvent) => {
    event.preventDefault(); setError('')
    if (!/^(https?:\/\/|\/)/i.test(url)) return setError('Utiliza una URL HTTP(S) o una ruta interna')
    onInsert({ url, alt: alt || 'Imagen' })
  }
  return <Modal title="Insertar imagen" description="Sube una imagen privada, reutiliza una del documento o enlaza una dirección externa." onClose={onClose} size="large">
    <div className="modal-body form-stack">
      <div className="dialog-tabs"><button type="button" className={tab === 'upload' ? 'active' : ''} onClick={() => setTab('upload')}><Upload size={16} /> Subir</button><button type="button" className={tab === 'library' ? 'active' : ''} onClick={() => setTab('library')}><ImagePlus size={16} /> Este documento <em>{images.length}</em></button><button type="button" className={tab === 'url' ? 'active' : ''} onClick={() => setTab('url')}><Link2 size={16} /> URL</button></div>
      {tab === 'upload' && <form className="form-stack" onSubmit={submitFile}>
        <label className={`image-dropzone ${file ? 'has-file' : ''}`} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); chooseFile(Array.from(event.dataTransfer.files).find(item => item.type.startsWith('image/')) || null) }}><input type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={event => chooseFile(event.target.files?.[0] || null)} /><ImagePlus size={31} /><strong>{file ? file.name : 'Selecciona o arrastra una imagen'}</strong><span>{file ? `${(file.size / 1024 / 1024).toLocaleString('es-ES', { maximumFractionDigits: 2 })} MB` : 'PNG, JPEG, WebP o GIF · almacenamiento privado y replicado'}</span></label>
        <label className="field"><span>Texto alternativo</span><input value={alt} onChange={event => setAlt(event.target.value)} placeholder="Describe el contenido de la imagen" /></label>
        {error && <div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancelar</button><button className="button primary" disabled={saving || !file}>{saving ? 'Subiendo…' : 'Subir e insertar'}</button></div>
      </form>}
      {tab === 'library' && <>{images.length ? <div className="document-image-library">{images.map(image => <button type="button" key={image.id} onClick={() => onInsert({ url: image.url, alt: image.filename.replace(/\.[^.]+$/, '') })}><img src={image.url} alt="" loading="lazy" /><span><strong>{image.filename}</strong><small>{(image.size / 1024).toLocaleString('es-ES', { maximumFractionDigits: 0 })} KB</small></span></button>)}</div> : <div className="dialog-empty image-empty"><ImagePlus size={30} /><strong>Este documento todavía no tiene imágenes</strong><span>Sube la primera desde la pestaña anterior.</span></div>}<div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancelar</button></div></>}
      {tab === 'url' && <form className="form-stack" onSubmit={submitUrl}><label className="field"><span>Dirección de la imagen</span><input autoFocus value={url} onChange={event => setUrl(event.target.value)} placeholder="https://…" required /></label><label className="field"><span>Texto alternativo</span><input value={alt} onChange={event => setAlt(event.target.value)} placeholder="Describe el contenido de la imagen" /></label>{error && <div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancelar</button><button className="button primary">Insertar imagen</button></div></form>}
    </div>
  </Modal>
}

function TableDialog({ onClose, onInsert }: { onClose: () => void; onInsert: (value: string) => void }) {
  const [columns, setColumns] = useState(3)
  const [rows, setRows] = useState(3)
  const [header, setHeader] = useState(true)
  const create = () => {
    const headings = Array.from({ length: columns }, (_, index) => header ? `Columna ${index + 1}` : ' ')
    const separator = Array.from({ length: columns }, () => '---')
    const body = Array.from({ length: rows }, () => `| ${Array.from({ length: columns }, () => 'Contenido').join(' | ')} |`)
    onInsert(`| ${headings.join(' | ')} |\n| ${separator.join(' | ')} |\n${body.join('\n')}`)
  }
  return <Modal title="Insertar tabla" description="Genera una tabla Markdown compatible con alineación y edición posterior." onClose={onClose}>
    <div className="modal-body form-stack"><div className="form-grid"><label className="field"><span>Columnas</span><input type="number" min="2" max="10" value={columns} onChange={event => setColumns(Math.max(2, Math.min(10, Number(event.target.value))))} /></label><label className="field"><span>Filas de contenido</span><input type="number" min="1" max="30" value={rows} onChange={event => setRows(Math.max(1, Math.min(30, Number(event.target.value))))} /></label></div><label className="check-field"><input type="checkbox" checked={header} onChange={event => setHeader(event.target.checked)} /> Primera fila como cabecera</label><div className="table-mini-preview">{Array.from({ length: Math.min(rows + 1, 5) }, (_, row) => <div key={row}>{Array.from({ length: columns }, (_, column) => <span className={row === 0 && header ? 'header' : ''} key={column} />)}</div>)}</div><div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancelar</button><button type="button" className="button primary" onClick={create}><Table2 size={17} /> Insertar tabla</button></div></div>
  </Modal>
}

function DiagramStudio({ draft, onClose, onInsert }: { draft: { code: string; editing: boolean }; onClose: () => void; onInsert: (code: string) => void }) {
  const [code, setCode] = useState(draft.code)
  const [template, setTemplate] = useState(draft.editing ? '' : diagramTemplates[0].id)
  return <Modal title={draft.editing ? 'Editar diagrama' : 'Estudio de diagramas'} description="Construye el diagrama con Mermaid y comprueba el resultado antes de insertarlo." onClose={onClose} size="large">
    <div className="diagram-studio">
      <aside className="diagram-template-panel"><span>TIPO DE DIAGRAMA</span>{diagramTemplates.map(item => <button type="button" className={template === item.id ? 'active' : ''} key={item.id} onClick={() => { setTemplate(item.id); setCode(item.code) }}><Workflow size={17} /><span><strong>{item.name}</strong><small>{item.description}</small></span></button>)}</aside>
      <div className="diagram-editor-panel"><div className="diagram-panel-heading"><span><Code2 size={15} /> DEFINICIÓN MERMAID</span><a href="https://mermaid.js.org/intro/" target="_blank" rel="noreferrer">Referencia de sintaxis</a></div><textarea value={code} onChange={event => { setCode(event.target.value); setTemplate('') }} spellCheck={false} aria-label="Definición Mermaid" /></div>
      <div className="diagram-preview-panel"><div className="diagram-panel-heading"><span><Eye size={15} /> RESULTADO</span><span>Actualización automática</span></div><MermaidDiagram definition={code} title="Vista previa" controls={false} /></div>
      <div className="diagram-studio-actions"><span>El diagrama se guardará como texto Markdown y seguirá siendo editable.</span><div><button type="button" className="button secondary" onClick={onClose}>Cancelar</button><button type="button" className="button primary" onClick={() => onInsert(code)} disabled={!code.trim()}><Workflow size={17} /> {draft.editing ? 'Actualizar diagrama' : 'Insertar diagrama'}</button></div></div>
    </div>
  </Modal>
}

function EditorHelp({ onClose }: { onClose: () => void }) {
  return <Modal title="Guía rápida del editor" description="Formato admitido y atajos disponibles." onClose={onClose} size="large">
    <div className="modal-body editor-help-grid">
      <section><h3>Texto</h3><dl><div><dt>Negrita</dt><dd><code>**texto**</code></dd></div><div><dt>Cursiva</dt><dd><code>*texto*</code></dd></div><div><dt>Tachado</dt><dd><code>~~texto~~</code></dd></div><div><dt>Enlace</dt><dd><code>[texto](url)</code></dd></div></dl></section>
      <section><h3>Bloques</h3><dl><div><dt>Título</dt><dd><code>## Título</code></dd></div><div><dt>Cita</dt><dd><code>&gt; nota</code></dd></div><div><dt>Tarea</dt><dd><code>- [ ] pendiente</code></dd></div><div><dt>Diagrama</dt><dd><code>```mermaid</code></dd></div></dl></section>
      <section><h3>Atajos</h3><dl><div><dt>Guardar</dt><dd><kbd>Ctrl</kbd> + <kbd>S</kbd></dd></div><div><dt>Negrita</dt><dd><kbd>Ctrl</kbd> + <kbd>B</kbd></dd></div><div><dt>Cursiva</dt><dd><kbd>Ctrl</kbd> + <kbd>I</kbd></dd></div><div><dt>Enlace</dt><dd><kbd>Ctrl</kbd> + <kbd>K</kbd></dd></div></dl></section>
      <section><h3>Imágenes</h3><p>Puedes subirlas desde el botón de imagen, arrastrarlas sobre el editor o pegar una captura directamente desde el portapapeles.</p></section>
      <div className="modal-actions"><button type="button" className="button primary" onClick={onClose}>Entendido</button></div>
    </div>
  </Modal>
}
