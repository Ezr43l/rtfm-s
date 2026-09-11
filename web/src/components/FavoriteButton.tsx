import { Star } from 'lucide-react'
import { useState } from 'react'
import { useFavorites } from '../context/FavoritesContext'
import type { DocumentMeta } from '../types'
import { Toast } from './Toast'

export function FavoriteButton({ document, showLabel = false }: { document: DocumentMeta; showLabel?: boolean }) {
  const { isFavorite, toggle } = useFavorites()
  const [pending, setPending] = useState(false)
  const [notice, setNotice] = useState<{ message: string; tone: 'success' | 'error' } | null>(null)
  const active = isFavorite(document.id)
  if (document.status === 'deleted') return null

  const change = async (event: React.MouseEvent) => {
    event.preventDefault()
    event.stopPropagation()
    if (pending) return
    setPending(true)
    try {
      const favorite = await toggle(document)
      setNotice({ message: favorite ? 'Documento añadido a favoritos' : 'Documento retirado de favoritos', tone: 'success' })
    } catch (caught) {
      setNotice({ message: caught instanceof Error ? caught.message : 'No se pudo actualizar el favorito', tone: 'error' })
    } finally {
      setPending(false)
    }
  }

  return <>
    <button
      type="button"
      className={`favorite-button ${active ? 'active' : ''} ${showLabel ? 'with-label' : ''}`}
      onClick={event => void change(event)}
      disabled={pending}
      aria-pressed={active}
      title={active ? 'Quitar de favoritos' : 'Añadir a favoritos'}
    ><Star size={showLabel ? 17 : 16} fill={active ? 'currentColor' : 'none'} />{showLabel && <span>{active ? 'En favoritos' : 'Favorito'}</span>}</button>
    {notice && <Toast message={notice.message} tone={notice.tone} onDismiss={() => setNotice(null)} />}
  </>
}
