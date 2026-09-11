import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../lib/api'
import type { DocumentMeta, FavoriteDocument } from '../types'
import { useAuth } from './AuthContext'

interface FavoriteMutation {
  favorite: boolean
  document: FavoriteDocument
}

interface FavoritesValue {
  documents: FavoriteDocument[]
  loading: boolean
  error: string
  isFavorite: (documentId: string) => boolean
  toggle: (document: DocumentMeta) => Promise<boolean>
  refresh: () => Promise<void>
}

const FavoritesContext = createContext<FavoritesValue | null>(null)

export function FavoritesProvider({ children }: { children: ReactNode }) {
  const { session, loading: authLoading } = useAuth()
  const [documents, setDocuments] = useState<FavoriteDocument[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const favoriteIds = useMemo(() => new Set(documents.map(document => document.id)), [documents])

  const refresh = useCallback(async () => {
    if (!session?.user_id) { setDocuments([]); return }
    setLoading(true); setError('')
    try {
      const result = await api<{ items: FavoriteDocument[] }>('/favorites')
      setDocuments(result.items)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'No se pudieron cargar los favoritos')
      throw caught
    } finally {
      setLoading(false)
    }
  }, [session?.user_id])

  useEffect(() => {
    if (authLoading) return
    if (!session?.user_id) { setDocuments([]); return }
    void refresh().catch(() => undefined)
  }, [authLoading, refresh, session?.user_id])

  const toggle = useCallback(async (document: DocumentMeta) => {
    const removing = favoriteIds.has(document.id)
    const optimistic = { ...document, favorited_at: new Date().toISOString() }
    setDocuments(current => removing ? current.filter(item => item.id !== document.id) : [optimistic, ...current])
    try {
      const result = await api<FavoriteMutation>(`/favorites/${document.id}`, { method: removing ? 'DELETE' : 'PUT' })
      setDocuments(current => result.favorite
        ? [result.document, ...current.filter(item => item.id !== document.id)]
        : current.filter(item => item.id !== document.id))
      return result.favorite
    } catch (error) {
      await refresh().catch(() => undefined)
      throw error
    }
  }, [favoriteIds, refresh])

  const value = useMemo(() => ({ documents, loading, error, isFavorite: (id: string) => favoriteIds.has(id), toggle, refresh }), [documents, error, favoriteIds, loading, refresh, toggle])
  return <FavoritesContext.Provider value={value}>{children}</FavoritesContext.Provider>
}

export function useFavorites() {
  const value = useContext(FavoritesContext)
  if (!value) throw new Error('useFavorites debe usarse dentro de FavoritesProvider')
  return value
}
