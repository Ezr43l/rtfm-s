import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { EmptyState, ErrorState, LoadingState } from './components/Feedback'
import { AuthProvider, useAuth } from './context/AuthContext'
import { FavoritesProvider } from './context/FavoritesContext'
import { ThemeProvider } from './context/ThemeContext'
import { AppShell, PassiveNode } from './layout/AppShell'
import { api } from './lib/api'
import { hasFullControl } from './lib/permissions'
import { ArchivePage } from './pages/ArchivePage'
import { DashboardPage } from './pages/DashboardPage'
import { DocumentPage } from './pages/DocumentPage'
import { FavoritesPage } from './pages/FavoritesPage'
import { LibrariesPage } from './pages/LibrariesPage'
import { LibraryPage } from './pages/LibraryPage'
import { LoginPage } from './pages/LoginPage'
import { LogsPage } from './pages/LogsPage'
import { ProfilePage } from './pages/ProfilePage'
import { SearchPage } from './pages/SearchPage'
import { SetupPage } from './pages/SetupPage'
import { ClusterPage, SystemSettingsPage } from './pages/SystemPage'
import { TagsPage } from './pages/TagsPage'
import { TrashPage } from './pages/TrashPage'
import { UsersPage } from './pages/UsersPage'
import type { PublicSystemStatus } from './types'
import './styles.css'

function Protected({ children }: { children: React.ReactNode }) {
  const { session, loading } = useAuth()
  const location = useLocation()
  if (loading) return <LoadingState label="Comprobando la sesión…" />
  if (!session) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return children
}

function FullControl({ children }: { children: React.ReactNode }) {
  const { session } = useAuth()
  if (!hasFullControl(session?.role)) return <ErrorState message="Esta página requiere una cuenta personal con control total." />
  return children
}

function ApplicationRoutes({ status }: { status: PublicSystemStatus }) {
  return <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<Protected><AppShell status={status} /></Protected>}>
      <Route index element={<Navigate to="/dashboard" replace />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/libraries" element={<LibrariesPage />} />
      <Route path="/libraries/:libraryId" element={<LibraryPage />} />
      <Route path="/favorites" element={<FavoritesPage />} />
      <Route path="/documents/:documentId" element={<DocumentPage />} />
      <Route path="/documents/:documentId/edit" element={<DocumentPage />} />
      <Route path="/search" element={<SearchPage />} />
      <Route path="/tags" element={<TagsPage />} />
      <Route path="/archive" element={<ArchivePage />} />
      <Route path="/trash" element={<TrashPage />} />
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/settings/users" element={<FullControl><UsersPage /></FullControl>} />
      <Route path="/administration/cluster" element={<ClusterPage />} />
      <Route path="/settings/logs" element={<FullControl><LogsPage /></FullControl>} />
      <Route path="/settings/system" element={<FullControl><SystemSettingsPage /></FullControl>} />
      <Route path="*" element={<EmptyState title="Página no encontrada" description="La dirección solicitada no existe en RTFM." />} />
    </Route>
  </Routes>
}

function App() {
  const [status, setStatus] = useState<PublicSystemStatus | null>(null)
  const [error, setError] = useState('')
  const load = () => { setError(''); api<PublicSystemStatus>('/public-status').then(setStatus).catch(caught => setError(caught.message)) }
  useEffect(() => {
    load()
    const interval = window.setInterval(load, 15_000)
    return () => window.clearInterval(interval)
  }, [])
  if (error) return <main className="boot-page"><ErrorState message={error} retry={load} /></main>
  if (!status) return <main className="boot-page"><LoadingState label="Conectando con el nodo…" /></main>
  if (status.setup_required) return <SetupPage />
  if (status.role !== 'active') return <PassiveNode status={status} />
  return <ApplicationRoutes status={status} />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider><AuthProvider><FavoritesProvider><BrowserRouter><App /></BrowserRouter></FavoritesProvider></AuthProvider></ThemeProvider>
  </StrictMode>,
)
