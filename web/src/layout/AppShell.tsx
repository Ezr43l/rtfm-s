import {
  Archive, BookOpen, Boxes, ChevronLeft, ChevronRight, CircleUserRound, FileSearch,
  LayoutDashboard, Library, Menu, Moon, Network, ScrollText, Settings, Star, Sun, Tags, Trash2, UserRound, UsersRound, X,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { hasFullControl } from '../lib/permissions'
import type { PublicSystemStatus } from '../types'

const mainNavigation = [
  { to: '/dashboard', label: 'Inicio', icon: LayoutDashboard },
  { to: '/libraries', label: 'Bibliotecas', icon: Library },
  { to: '/favorites', label: 'Favoritos', icon: Star },
  { to: '/search', label: 'Buscar', icon: FileSearch },
  { to: '/tags', label: 'Etiquetas', icon: Tags },
  { to: '/archive', label: 'Archivados', icon: Archive },
  { to: '/trash', label: 'Papelera', icon: Trash2 },
]

const settingsNavigation = [
  { to: '/profile', label: 'Mi perfil', icon: UserRound },
  { to: '/settings/users', label: 'Usuarios', icon: UsersRound, fullControl: true },
  { to: '/administration/cluster', label: 'Nodos y HA', icon: Network },
  { to: '/settings/logs', label: 'Registros', icon: ScrollText, fullControl: true },
  { to: '/settings/system', label: 'Configuración', icon: Settings },
]

type NavigationItem = { to: string; label: string; icon: typeof LayoutDashboard; fullControl?: boolean }

function NavigationGroup({ label, items, collapsed, closeMobile }: { label: string; items: NavigationItem[]; collapsed: boolean; closeMobile: () => void }) {
  return <div className="nav-group">
    {!collapsed && <span className="nav-group-label">{label}</span>}
    {items.map(item => <NavLink key={item.to} to={item.to} onClick={closeMobile} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} title={collapsed ? item.label : undefined}>
      <item.icon size={19} /><span>{item.label}</span>
    </NavLink>)}
  </div>
}

export function AppShell({ status }: { status: PublicSystemStatus }) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [query, setQuery] = useState('')
  const { theme, toggle } = useTheme()
  const { session, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const visibleSettings = settingsNavigation.filter(item => !item.fullControl || hasFullControl(session?.role))

  const submitSearch = (event: React.FormEvent) => {
    event.preventDefault()
    if (query.trim()) navigate(`/search?q=${encodeURIComponent(query.trim())}`)
  }

  return <div className={`application ${collapsed ? 'sidebar-collapsed' : ''}`}>
    {mobileOpen && <button className="mobile-overlay" aria-label="Cerrar menú" onClick={() => setMobileOpen(false)} />}
    <aside className={`sidebar ${mobileOpen ? 'mobile-open' : ''}`}>
      <div className="brand">
        <img src="/icono.svg" alt="" />
        {!collapsed && <div><strong>RTFM</strong><span>Conocimiento operativo</span></div>}
        <button className="icon-button mobile-close" onClick={() => setMobileOpen(false)}><X size={20} /></button>
      </div>
      <nav aria-label="Navegación principal">
        <NavigationGroup label="DOCUMENTACIÓN" items={mainNavigation} collapsed={collapsed} closeMobile={() => setMobileOpen(false)} />
        <NavigationGroup label="ADMINISTRACIÓN" items={visibleSettings} collapsed={collapsed} closeMobile={() => setMobileOpen(false)} />
      </nav>
      <div className="sidebar-footer">
        <div className={`node-card ${status.role}`} title={status.role_reason}>
          <span className="status-dot" />
          {!collapsed && <div><strong>{status.node}</strong><span>Nodo {status.role === 'active' ? 'activo' : status.role}</span></div>}
        </div>
        <button className="collapse-button" onClick={() => setCollapsed(value => !value)}>{collapsed ? <ChevronRight size={18} /> : <><ChevronLeft size={18} /><span>Contraer menú</span></>}</button>
      </div>
    </aside>
    <div className="app-column">
      <header className="topbar">
        <button className="icon-button mobile-menu" onClick={() => setMobileOpen(true)}><Menu size={21} /></button>
        <form className="global-search" onSubmit={submitSearch}>
          <FileSearch size={18} />
          <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Buscar en toda la documentación…" aria-label="Buscar" />
          <kbd>Enter</kbd>
        </form>
        <div className="topbar-actions">
          <button className="icon-button" onClick={toggle} title={theme === 'dark' ? 'Usar tema claro' : 'Usar tema oscuro'}>{theme === 'dark' ? <Sun size={19} /> : <Moon size={19} />}</button>
          <NavLink to="/profile" className="user-chip" title="Abrir mi perfil"><CircleUserRound size={20} /><div><strong>{session?.display_name || session?.actor}</strong><span>@{session?.actor}</span></div></NavLink>
          <button className="button ghost logout-button" onClick={() => void logout()}>Salir</button>
        </div>
      </header>
      <main className="page" key={location.pathname}><Outlet /></main>
    </div>
  </div>
}

export function PassiveNode({ status }: { status: PublicSystemStatus }) {
  const { theme, toggle } = useTheme()
  const unknown = status.role === 'unknown'
  return <main className="passive-page">
    <button className="icon-button passive-theme" onClick={toggle}>{theme === 'dark' ? <Sun /> : <Moon />}</button>
    <section className="passive-card">
      <img src="/icono.svg" alt="" />
      <span className="eyebrow">RTFM · ALTA DISPONIBILIDAD</span>
      <h1>{unknown ? 'No se puede determinar el nodo activo' : 'Este nodo está en espera'}</h1>
      <p>{unknown
        ? <><strong>{status.node}</strong> mantiene las escrituras bloqueadas porque todavía no dispone de una IP flotante verificable.</>
        : <><strong>{status.node}</strong> funciona correctamente, pero no posee ahora la IP flotante. Las escrituras están bloqueadas para evitar conflictos.</>}</p>
      <div className="passive-status"><span className="status-dot" /><div><strong>{unknown ? 'Estado sin verificar' : 'Servicio disponible'}</strong><span>{status.floating_ip_connector.error || status.role_reason}</span></div></div>
      {status.active_url && <a className="button primary wide" href={status.active_url}>Abrir el nodo activo</a>}
      <div className="passive-meta"><span>Versión {status.version}</span><span>Sincronización cada {Math.round(status.sync_interval_seconds / 60)} min</span></div>
    </section>
  </main>
}

export function ContentCard({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`content-card ${className}`}>{children}</section>
}
