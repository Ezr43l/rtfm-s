import { ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { api, jsonBody } from '../lib/api'
import { roleLabels } from '../lib/permissions'
import type { AccessRole, LibraryPermissionGrant, LibraryPermissions } from '../types'
import { LoadingState } from './Feedback'
import { Modal } from './Modal'

const roles: AccessRole[] = ['reader', 'operator', 'full_control']
const levels: Record<AccessRole, number> = { reader: 0, operator: 1, full_control: 2 }

export function LibraryPermissionsDialog({ libraryId, onClose, onSaved }: {
  libraryId: string
  onClose: () => void
  onSaved: () => void
}) {
  const { session } = useAuth()
  const [data, setData] = useState<LibraryPermissions | null>(null)
  const [mode, setMode] = useState<'open' | 'restricted'>('open')
  const [grants, setGrants] = useState<Record<string, AccessRole>>({})
  const [password, setPassword] = useState('')
  const [otp, setOtp] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api<LibraryPermissions>(`/libraries/${libraryId}/permissions`).then(result => {
      setData(result)
      setMode(result.mode)
      setGrants(Object.fromEntries(result.grants.map(grant => [`${grant.subject_type}:${grant.subject_id}`, grant.role])))
    }).catch(caught => setError(caught instanceof Error ? caught.message : 'No se pudieron cargar los permisos'))
  }, [libraryId])

  const assignable = useMemo(
    () => data?.subjects.filter(subject => !(subject.identity_type === 'person' && subject.role === 'full_control')) || [],
    [data],
  )

  const changeGrant = (key: string, role: string) => {
    setGrants(current => {
      const next = { ...current }
      if (role) next[key] = role as AccessRole
      else delete next[key]
      return next
    })
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    const payloadGrants: LibraryPermissionGrant[] = mode === 'open' ? [] : assignable.flatMap(subject => {
      const subjectType = subject.identity_type === 'person' ? 'user' : 'api_client'
      const role = grants[`${subjectType}:${subject.id}`]
      return role ? [{ subject_type: subjectType, subject_id: subject.id, role }] : []
    })
    try {
      await api(`/libraries/${libraryId}/permissions`, {
        method: 'PUT',
        ...jsonBody({ mode, grants: payloadGrants, current_password: password, otp: otp || null }),
      })
      onSaved()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'No se pudieron guardar los permisos')
    } finally {
      setSaving(false)
    }
  }

  return <Modal
    title="Permisos de la biblioteca"
    description="Limita quién puede ver o modificar esta biblioteca sin superar nunca su nivel global."
    onClose={onClose}
    size="large"
  >
    {!data ? <div className="modal-body">{error ? <div className="form-error">{error}</div> : <LoadingState label="Cargando identidades…" />}</div> : <form className="modal-body form-stack" onSubmit={submit}>
      <fieldset className="permission-mode">
        <legend>Visibilidad</legend>
        <label><input type="radio" name="access-mode" checked={mode === 'open'} onChange={() => setMode('open')} /><span><strong>Abierta a identidades autenticadas</strong><small>Cada persona o cliente API conserva su nivel global.</small></span></label>
        <label><input type="radio" name="access-mode" checked={mode === 'restricted'} onChange={() => setMode('restricted')} /><span><strong>Restringida por identidad</strong><small>Sin una concesión explícita, la biblioteca ni siquiera aparece.</small></span></label>
      </fieldset>

      {mode === 'restricted' && <div className="permission-subjects">
        <div className="permission-note"><ShieldCheck size={17} /><span>Las cuentas humanas con control total conservan acceso de recuperación y no pueden quedar bloqueadas.</span></div>
        {assignable.length ? assignable.map(subject => {
          const subjectType = subject.identity_type === 'person' ? 'user' : 'api_client'
          const key = `${subjectType}:${subject.id}`
          const label = subject.identity_type === 'person' ? subject.display_name || subject.username : subject.name
          return <label className="permission-subject" key={key}>
            <span><strong>{label}</strong><small>{subject.identity_type === 'person' ? `Persona · @${subject.username}` : 'Cliente API'} · máximo {roleLabels[subject.role]}</small></span>
            <select value={grants[key] || ''} onChange={event => changeGrant(key, event.target.value)} aria-label={`Permiso para ${label}`}>
              <option value="">Sin acceso</option>
              {roles.filter(role => levels[role] <= levels[subject.role]).map(role => <option value={role} key={role}>{roleLabels[role]}</option>)}
            </select>
          </label>
        }) : <p className="muted-copy">No hay otras identidades activas a las que conceder acceso.</p>}
      </div>}

      <div className="admin-confirmation">
        <p>Confirma tu identidad para aplicar este cambio sensible.</p>
        <label className="field"><span>Contraseña actual</span><input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required /></label>
        {session?.two_factor_enabled && <label className="field"><span>Código 2FA o recuperación</span><input inputMode="numeric" autoComplete="one-time-code" value={otp} onChange={event => setOtp(event.target.value)} required /></label>}
      </div>
      {error && <div className="form-error">{error}</div>}
      <div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancelar</button><button className="button primary" disabled={saving}><ShieldCheck size={17} /> {saving ? 'Guardando…' : 'Guardar permisos'}</button></div>
    </form>}
  </Modal>
}
