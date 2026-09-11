import { useState } from 'react'
import { api, jsonBody } from '../lib/api'
import type { Library } from '../types'
import { Modal } from './Modal'

const colors = ['indigo', 'blue', 'green', 'amber', 'rose']

export function LibraryDialog({ library, onClose, onSaved }: {
  library?: Library
  onClose: () => void
  onSaved: () => void
}) {
  const editing = Boolean(library)
  const [name, setName] = useState(library?.name || '')
  const [description, setDescription] = useState(library?.description || '')
  const [color, setColor] = useState(library?.color || 'indigo')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const payload = editing ? { name, description, color } : { name, description, color, icon: 'library' }
      await api(editing ? `/libraries/${library?.id}` : '/libraries', {
        method: editing ? 'PATCH' : 'POST',
        ...jsonBody(payload),
      })
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'No se pudo guardar la biblioteca')
    } finally {
      setSaving(false)
    }
  }

  return <Modal
    title={editing ? 'Editar biblioteca' : 'Nueva biblioteca'}
    description={editing ? 'Corrige el nombre, completa la descripción o cambia su color identificativo.' : 'Será la raíz de un árbol documental independiente.'}
    onClose={onClose}
  >
    <form onSubmit={submit} className="modal-body form-stack">
      <label className="field"><span>Nombre</span><input autoFocus value={name} onChange={event => setName(event.target.value)} placeholder="Ej. Infraestructura" required maxLength={160} /></label>
      <label className="field"><span>Descripción <small>Opcional</small></span><textarea value={description} onChange={event => setDescription(event.target.value)} rows={4} maxLength={1000} placeholder="Qué tipo de conocimiento contendrá…" /></label>
      <fieldset className="color-picker"><legend>Color identificativo</legend>{colors.map(value => <button type="button" aria-label={value} className={`color-dot ${value} ${color === value ? 'selected' : ''}`} onClick={() => setColor(value)} key={value} />)}</fieldset>
      {error && <div className="form-error">{error}</div>}
      <div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancelar</button><button className="button primary" disabled={saving}>{saving ? 'Guardando…' : editing ? 'Guardar cambios' : 'Crear biblioteca'}</button></div>
    </form>
  </Modal>
}
