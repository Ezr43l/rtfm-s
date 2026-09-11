import { Star } from 'lucide-react'
import { DocumentTable } from '../components/DocumentTable'
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../components/Feedback'
import { useFavorites } from '../context/FavoritesContext'

export function FavoritesPage() {
  const { documents, error, loading, refresh } = useFavorites()
  return <>
    <PageHeader eyebrow="SELECCIÓN PERSONAL" title="Favoritos" description="Documentos que has marcado como importantes para acceder a ellos inmediatamente." />
    {error && !documents.length ? <ErrorState message={error} retry={() => void refresh().catch(() => undefined)} /> : loading && !documents.length ? <LoadingState label="Preparando tus favoritos…" /> : documents.length
      ? <DocumentTable documents={documents} />
      : <EmptyState icon={<Star size={38} />} title="Todavía no tienes favoritos" description="Pulsa la estrella de cualquier documento para mantenerlo siempre a mano." />}
  </>
}
