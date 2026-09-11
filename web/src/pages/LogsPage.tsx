import { ChevronDown, ChevronLeft, ChevronRight, Download, Filter, RefreshCw, ScrollText } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../components/Feedback'
import { api, formatDate } from '../lib/api'
import type { AuditEvent } from '../types'

interface LogPage { items: AuditEvent[]; next_cursor: string | null; has_more: boolean; count: number }
interface Filters { period: string; level: string; actor: string; action: string; node: string; source: string; result: string }
const initialFilters: Filters = { period: '24h', level: '', actor: '', action: '', node: '', source: '', result: '' }

function periodBounds(period: string) {
  if (period === 'all') return {}
  const durations: Record<string, number> = { '24h': 86400000, '7d': 604800000, '30d': 2592000000, '365d': 31536000000 }
  const now = new Date()
  return { from: new Date(now.getTime() - durations[period]).toISOString(), to: now.toISOString() }
}

function paramsFor(filters: Filters, limit: number, cursor?: string | null) {
  const params = new URLSearchParams({ limit: String(limit) })
  for (const [key, value] of Object.entries(periodBounds(filters.period))) params.set(key, value)
  for (const key of ['level', 'actor', 'action', 'node', 'source', 'result'] as const) if (filters[key]) params.set(key, filters[key])
  if (cursor) params.set('cursor', cursor)
  return params
}

export function LogsPage() {
  const [draft, setDraft] = useState<Filters>(initialFilters)
  const [filters, setFilters] = useState<Filters>(initialFilters)
  const [limit, setLimit] = useState(50)
  const [page, setPage] = useState<LogPage | null>(null)
  const [pageNumber, setPageNumber] = useState(1)
  const [cursor, setCursor] = useState<string | null>(null)
  const [history, setHistory] = useState<(string | null)[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [downloading, setDownloading] = useState(false)

  const load = useCallback((targetCursor: string | null = null) => {
    setLoading(true); setError('')
    api<LogPage>(`/logs?${paramsFor(filters, limit, targetCursor)}`).then(setPage).catch(caught => setError(caught.message)).finally(() => setLoading(false))
  }, [filters, limit])
  useEffect(() => { setCursor(null); setHistory([]); setPageNumber(1); load(null) }, [load])

  const apply = (event: React.FormEvent) => { event.preventDefault(); setFilters({ ...draft }) }
  const next = () => {
    if (!page?.next_cursor) return
    setHistory(items => [...items, cursor]); setCursor(page.next_cursor); setPageNumber(value => value + 1); load(page.next_cursor)
  }
  const previous = () => {
    if (!history.length) return
    const target = history[history.length - 1]
    setHistory(items => items.slice(0, -1)); setCursor(target); setPageNumber(value => Math.max(1, value - 1)); load(target)
  }
  const download = async (format: 'jsonl' | 'csv') => {
    setDownloading(true); setError('')
    try {
      const query = paramsFor(filters, 200)
      query.delete('limit'); query.delete('from'); query.delete('to'); query.set('range', filters.period); query.set('format', format)
      const response = await fetch(`/api/v1/logs/export?${query}`, { credentials: 'same-origin' })
      if (!response.ok) throw new Error('No se pudo generar la descarga')
      const blob = await response.blob(); const url = URL.createObjectURL(blob); const anchor = document.createElement('a')
      anchor.href = url; anchor.download = `rtfm-${filters.period}.${format}`; anchor.click(); URL.revokeObjectURL(url)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo descargar el registro') }
    finally { setDownloading(false) }
  }
  const activeFilterCount = useMemo(() => Object.entries(filters).filter(([key, value]) => key !== 'period' && value).length, [filters])

  return <>
    <PageHeader eyebrow="AJUSTES · OBSERVABILIDAD" title="Registros" description="Auditoría completa de operaciones, accesos, sincronización y cambios documentales." actions={<button className="button secondary" onClick={() => load(cursor)}><RefreshCw size={17} /> Actualizar</button>} />
    <form className="log-filters" onSubmit={apply}>
      <label className="field compact"><span>Periodo</span><select value={draft.period} onChange={event => setDraft({ ...draft, period: event.target.value })}><option value="24h">Últimas 24 horas</option><option value="7d">Última semana</option><option value="30d">Último mes</option><option value="365d">Último año</option><option value="all">Histórico completo</option></select></label>
      <label className="field compact"><span>Nivel</span><select value={draft.level} onChange={event => setDraft({ ...draft, level: event.target.value })}><option value="">Todos</option><option value="info">Información</option><option value="warning">Aviso</option><option value="error">Error</option></select></label>
      <label className="field compact grow"><span>Autor</span><input value={draft.actor} onChange={event => setDraft({ ...draft, actor: event.target.value })} placeholder="Usuario o aplicación" /></label>
      <label className="field compact grow"><span>Acción</span><input value={draft.action} onChange={event => setDraft({ ...draft, action: event.target.value })} placeholder="Ej. document.update" /></label>
      <label className="field compact"><span>Resultado</span><select value={draft.result} onChange={event => setDraft({ ...draft, result: event.target.value })}><option value="">Todos</option><option value="ok">Correcto</option><option value="error">Error</option></select></label>
      <button className="button primary filter-button"><Filter size={17} /> Aplicar {activeFilterCount > 0 && <span>{activeFilterCount}</span>}</button>
    </form>
    <div className="log-toolbar"><label>Filas por página <select value={limit} onChange={event => setLimit(Number(event.target.value))}><option>25</option><option>50</option><option>100</option><option>200</option></select></label><div className="download-group"><button className="button secondary small" disabled={downloading} onClick={() => void download('csv')}><Download size={15} /> CSV</button><button className="button secondary small" disabled={downloading} onClick={() => void download('jsonl')}><Download size={15} /> JSONL</button></div></div>
    {error ? <ErrorState message={error} retry={() => load(cursor)} /> : loading ? <LoadingState label="Consultando registros…" /> : page?.items.length ? <>
      <div className="log-table">
        <div className="log-table-head"><span>Fecha y hora</span><span>Nivel</span><span>Autor</span><span>Nodo</span><span>Acción</span><span>Resultado</span><span /></div>
        {page.items.map(event => <LogRow event={event} key={event.event_id} />)}
      </div>
      <div className="pagination"><button className="button secondary small" disabled={!history.length} onClick={previous}><ChevronLeft size={16} /> Anterior</button><span>Página <strong>{pageNumber}</strong> · {page.count} registros</span><button className="button secondary small" disabled={!page.has_more} onClick={next}>Siguiente <ChevronRight size={16} /></button></div>
    </> : <EmptyState icon={<ScrollText size={38} />} title="No hay registros para estos filtros" description="Amplía el periodo o elimina algún filtro para consultar más operaciones." />}
  </>
}

function LogRow({ event }: { event: AuditEvent }) {
  const [open, setOpen] = useState(false)
  return <div className={`log-entry ${open ? 'expanded' : ''}`}>
    <button className="log-entry-main" onClick={() => setOpen(value => !value)}>
      <time>{formatDate(event.timestamp)}</time><span><span className={`level-badge ${event.level || 'info'}`}>{event.level || 'info'}</span></span><strong title={event.actor}>{event.actor}</strong><span>{event.node || '—'}</span><code>{event.action}</code><span><span className={`result-badge ${event.result}`}>{event.result || '—'}</span></span><ChevronDown size={16} />
    </button>
    {open && <div className="log-detail"><dl><div><dt>Evento</dt><dd>{event.event_id}</dd></div><div><dt>Operación</dt><dd>{event.operation_id}</dd></div><div><dt>Origen</dt><dd>{event.source}</dd></div><div><dt>Entidad</dt><dd>{event.entity_type || '—'} · {event.entity_id || '—'}</dd></div></dl><div className="log-json"><div><span>Antes</span><pre>{JSON.stringify(event.before ?? null, null, 2)}</pre></div><div><span>Después</span><pre>{JSON.stringify(event.after ?? null, null, 2)}</pre></div></div></div>}
  </div>
}
