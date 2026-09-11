import { Archive, BookOpen, FolderTree, Library, Network, Plus, Server, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../components/Feedback'
import { ContentCard } from '../layout/AppShell'
import { api, formatDate } from '../lib/api'
import type { DocumentMeta, SystemStatus } from '../types'

interface Dashboard {
  status: SystemStatus
  counts: { libraries: number; categories: number; documents: number; archived: number; deleted: number }
  recent_documents: DocumentMeta[]
}

export function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState('')
  const load = () => {
    setError('')
    api<Dashboard>('/dashboard').then(setData).catch(caught => setError(caught.message))
  }
  useEffect(load, [])
  if (error) return <ErrorState message={error} retry={load} />
  if (!data) return <LoadingState label="Preparando el espacio de trabajo…" />
  const metrics = [
    { label: 'Bibliotecas', value: data.counts.libraries, icon: Library, tone: 'violet' },
    { label: 'Categorías', value: data.counts.categories, icon: FolderTree, tone: 'blue' },
    { label: 'Documentos activos', value: data.counts.documents, icon: BookOpen, tone: 'green' },
    { label: 'Archivados', value: data.counts.archived, icon: Archive, tone: 'amber' },
  ]
  return <>
    <PageHeader eyebrow="PANEL GENERAL" title="Buenos días" description="Tu base de conocimiento está disponible y preparada para recibir contenido." actions={<Link className="button primary" to="/libraries"><Plus size={18} /> Crear contenido</Link>} />
    <div className="metric-grid">{metrics.map(metric => <ContentCard key={metric.label} className="metric-card"><div className={`metric-icon ${metric.tone}`}><metric.icon size={21} /></div><div><span>{metric.label}</span><strong>{metric.value}</strong></div></ContentCard>)}</div>
    <div className="dashboard-grid">
      <ContentCard className="recent-card">
        <div className="card-heading"><div><span className="eyebrow">CONTENIDO</span><h2>Documentos recientes</h2></div><Link to="/libraries">Ver bibliotecas</Link></div>
        {data.recent_documents.length ? <div className="recent-list">{data.recent_documents.map(document => <Link to={`/documents/${document.id}`} className="recent-document" key={document.id}><div className="document-glyph"><BookOpen size={18} /></div><div><strong>{document.title}</strong><span>{document.summary || 'Sin descripción'}</span></div><time>{formatDate(document.updated_at, false)}</time></Link>)}</div> : <EmptyState icon={<BookOpen size={34} />} title="Todavía no hay documentos" description="Crea una biblioteca y empieza a organizar el conocimiento de tus servidores." action={<Link className="button secondary" to="/libraries">Abrir bibliotecas</Link>} />}
      </ContentCard>
      <div className="dashboard-side">
        <ContentCard className="service-card">
          <div className="card-heading"><div><span className="eyebrow">ALTA DISPONIBILIDAD</span><h2>Estado del servicio</h2></div><span className="healthy-label"><ShieldCheck size={16} /> Operativo</span></div>
          <div className="service-node"><div className="server-illustration"><Server size={29} /></div><div><strong>{data.status.node}</strong><span>Nodo activo · versión {data.status.version}</span></div><span className="live-dot" /></div>
          <dl className="service-details"><div><dt>Reloj lógico</dt><dd>{data.status.sync.clock}</dd></div><div><dt>Última sincronización</dt><dd>{formatDate(data.status.sync.last_sync_at)}</dd></div><div><dt>Git documental</dt><dd>{data.status.git.ready ? 'Preparado' : 'Pendiente'}</dd></div></dl>
          <Link className="text-link" to="/administration/cluster"><Network size={16} /> Consultar nodos y replicación</Link>
        </ContentCard>
      </div>
    </div>
  </>
}
