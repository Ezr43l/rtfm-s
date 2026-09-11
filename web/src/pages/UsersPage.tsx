import {
  Ban, Bot, Check, Copy, KeyRound, Pencil, Plus, RotateCw, ShieldCheck, UserRound, UsersRound,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../components/Feedback'
import { Modal } from '../components/Modal'
import { Toast, type ToastTone } from '../components/Toast'
import { useAuth } from '../context/AuthContext'
import { ContentCard } from '../layout/AppShell'
import { api, formatDate, jsonBody } from '../lib/api'
import { copyText } from '../lib/clipboard'
import { roleLabels } from '../lib/permissions'
import type { AccessRole, ApiClient, ManagedUser } from '../types'

type Dialog =
  | { kind: 'create-user' }
  | { kind: 'edit-user'; user: ManagedUser }
  | { kind: 'reset-user'; user: ManagedUser }
  | { kind: 'create-api' }
  | { kind: 'edit-api'; client: ApiClient }
  | { kind: 'rotate-api'; client: ApiClient }
  | { kind: 'revoke-api'; client: ApiClient }

const roleDescriptions: Record<AccessRole, string> = {
  reader: 'Consulta documentos, etiquetas y búsquedas. No puede modificar contenido.',
  operator: 'Crea, edita, mueve y archiva. No puede eliminar ni restaurar contenido.',
  full_control: 'Incluye eliminación al vault y restauración. En personas permite administrar accesos.',
}

function RoleOptions() {
  return <>{(Object.keys(roleLabels) as AccessRole[]).map(role => <option value={role} key={role}>{roleLabels[role]}</option>)}</>
}

function RoleBadge({ role }: { role: AccessRole }) {
  return <span className={`access-badge ${role}`}>{roleLabels[role]}</span>
}

function ConfirmationFields({ password, setPassword, otp, setOtp, twoFactor }: {
  password: string; setPassword: (value: string) => void; otp: string; setOtp: (value: string) => void; twoFactor: boolean
}) {
  return <div className="confirmation-fields">
    <div><ShieldCheck size={18} /><span><strong>Confirma la operación</strong><small>Usa las credenciales de tu propia cuenta.</small></span></div>
    <label className="field"><span>Tu contraseña actual</span><input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required /></label>
    {twoFactor && <label className="field"><span>Código 2FA o de recuperación</span><input inputMode="numeric" autoComplete="one-time-code" value={otp} onChange={event => setOtp(event.target.value)} required /></label>}
  </div>
}

export function UsersPage() {
  const { session } = useAuth()
  const [tab, setTab] = useState<'people' | 'api'>('people')
  const [users, setUsers] = useState<ManagedUser[]>([])
  const [clients, setClients] = useState<ApiClient[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [dialog, setDialog] = useState<Dialog | null>(null)
  const [revealed, setRevealed] = useState<{ name: string; token: string } | null>(null)

  const load = useCallback(() => {
    setLoading(true); setError('')
    Promise.all([
      api<{ items: ManagedUser[] }>('/users'),
      api<{ items: ApiClient[] }>('/users/api-clients'),
    ]).then(([people, applications]) => { setUsers(people.items); setClients(applications.items) })
      .catch(caught => setError(caught.message)).finally(() => setLoading(false))
  }, [])
  useEffect(load, [load])

  const saved = (token?: { name: string; token: string }) => {
    setDialog(null)
    if (token) setRevealed(token)
    load()
  }

  return <>
    <PageHeader eyebrow="AJUSTES · SEGURIDAD" title="Usuarios y accesos API" description="Identidades nominales y aplicaciones autorizadas, con permisos aplicados por el servidor." actions={<button className="button primary" onClick={() => setDialog({ kind: tab === 'people' ? 'create-user' : 'create-api' })}><Plus size={18} /> {tab === 'people' ? 'Nueva persona' : 'Nueva aplicación'}</button>} />
    <div className="access-overview">
      {(Object.keys(roleLabels) as AccessRole[]).map(role => <ContentCard className="access-role-card" key={role}><RoleBadge role={role} /><p>{roleDescriptions[role]}</p></ContentCard>)}
    </div>
    <div className="access-tabs" role="tablist">
      <button role="tab" aria-selected={tab === 'people'} className={tab === 'people' ? 'active' : ''} onClick={() => setTab('people')}><UsersRound size={17} /> Personas <span>{users.length}</span></button>
      <button role="tab" aria-selected={tab === 'api'} className={tab === 'api' ? 'active' : ''} onClick={() => setTab('api')}><Bot size={17} /> Aplicaciones API <span>{clients.length}</span></button>
    </div>
    {error ? <ErrorState message={error} retry={load} /> : loading ? <LoadingState /> : tab === 'people' ?
      <PeopleTable users={users} currentUserId={session?.user_id || ''} onEdit={user => setDialog({ kind: 'edit-user', user })} onReset={user => setDialog({ kind: 'reset-user', user })} onCreate={() => setDialog({ kind: 'create-user' })} /> :
      <ApiTable clients={clients} onEdit={client => setDialog({ kind: 'edit-api', client })} onRotate={client => setDialog({ kind: 'rotate-api', client })} onRevoke={client => setDialog({ kind: 'revoke-api', client })} onCreate={() => setDialog({ kind: 'create-api' })} />}

    {dialog?.kind === 'create-user' && <CreateUserDialog twoFactor={Boolean(session?.two_factor_enabled)} onClose={() => setDialog(null)} onSaved={() => saved()} />}
    {dialog?.kind === 'edit-user' && <EditUserDialog user={dialog.user} twoFactor={Boolean(session?.two_factor_enabled)} onClose={() => setDialog(null)} onSaved={() => saved()} />}
    {dialog?.kind === 'reset-user' && <ResetUserDialog user={dialog.user} twoFactor={Boolean(session?.two_factor_enabled)} onClose={() => setDialog(null)} onSaved={() => saved()} />}
    {dialog?.kind === 'create-api' && <CreateApiDialog twoFactor={Boolean(session?.two_factor_enabled)} onClose={() => setDialog(null)} onSaved={(name, token) => saved({ name, token })} />}
    {dialog?.kind === 'edit-api' && <EditApiDialog client={dialog.client} twoFactor={Boolean(session?.two_factor_enabled)} onClose={() => setDialog(null)} onSaved={() => saved()} />}
    {(dialog?.kind === 'rotate-api' || dialog?.kind === 'revoke-api') && <ApiTokenActionDialog action={dialog.kind === 'rotate-api' ? 'rotate' : 'revoke'} client={dialog.client} twoFactor={Boolean(session?.two_factor_enabled)} onClose={() => setDialog(null)} onSaved={token => saved(token ? { name: dialog.client.name, token } : undefined)} />}
    {revealed && <TokenReveal value={revealed} onClose={() => setRevealed(null)} />}
  </>
}

function PeopleTable({ users, currentUserId, onEdit, onReset, onCreate }: { users: ManagedUser[]; currentUserId: string; onEdit: (user: ManagedUser) => void; onReset: (user: ManagedUser) => void; onCreate: () => void }) {
  if (!users.length) return <EmptyState title="No hay cuentas nominales" description="Crea la primera cuenta personal." action={<button className="button primary" onClick={onCreate}>Crear persona</button>} />
  return <div className="identity-table people-table">
    <div className="identity-table-head"><span>Persona</span><span>Permisos</span><span>Seguridad</span><span>Estado</span><span>Actividad</span><span /></div>
    {users.map(user => <div className="identity-row" key={user.id}>
      <div className="identity-name"><span className="identity-avatar"><UserRound size={19} /></span><span><strong>{user.display_name}{user.id === currentUserId && <em>Tú</em>}</strong><small>@{user.username}</small></span></div>
      <RoleBadge role={user.role} />
      <span className="security-summary">{user.two_factor_enabled ? <><ShieldCheck size={15} /> 2FA activo</> : <><KeyRound size={15} /> Solo contraseña</>}</span>
      <span className={`status-badge ${user.status}`}>{user.status === 'active' ? 'Activa' : 'Desactivada'}</span>
      <span className="identity-date">{formatDate(user.updated_at)}</span>
      <div className="identity-actions">{user.id === currentUserId ? <Link className="button secondary small" to="/profile"><UserRound size={15} /> Mi perfil</Link> : <><button className="button ghost small" onClick={() => onReset(user)}><KeyRound size={15} /> Clave</button><button className="button secondary small" onClick={() => onEdit(user)}><Pencil size={15} /> Gestionar</button></>}</div>
    </div>)}
  </div>
}

function ApiTable({ clients, onEdit, onRotate, onRevoke, onCreate }: { clients: ApiClient[]; onEdit: (client: ApiClient) => void; onRotate: (client: ApiClient) => void; onRevoke: (client: ApiClient) => void; onCreate: () => void }) {
  if (!clients.length) return <EmptyState icon={<Bot size={38} />} title="No hay aplicaciones registradas" description="Registra una aplicación para emitir su primer token privado." action={<button className="button primary" onClick={onCreate}>Registrar aplicación</button>} />
  return <div className="identity-table api-table">
    <div className="identity-table-head"><span>Aplicación</span><span>Permisos</span><span>Token</span><span>Estado</span><span>Último uso</span><span /></div>
    {clients.map(client => <div className="identity-row" key={client.id}>
      <div className="identity-name"><span className="identity-avatar api"><Bot size={19} /></span><span><strong>{client.name}</strong><small>{client.description || 'Sin descripción'}</small></span></div>
      <RoleBadge role={client.role} />
      <code className="token-prefix">{client.token_prefix}…</code>
      <span className={`status-badge ${client.expired ? 'expired' : client.status}`}>{client.expired ? 'Caducado' : client.status === 'active' ? 'Activo' : client.status === 'disabled' ? 'Desactivado' : 'Revocado'}</span>
      <span className="identity-date">{client.last_used_at ? formatDate(client.last_used_at) : 'Nunca'}</span>
      <div className="identity-actions"><button className="icon-button" title="Rotar token" onClick={() => onRotate(client)}><RotateCw size={16} /></button>{client.status !== 'revoked' && <button className="icon-button danger-text" title="Revocar token" onClick={() => onRevoke(client)}><Ban size={16} /></button>}<button className="button secondary small" onClick={() => onEdit(client)}><Pencil size={15} /> Gestionar</button></div>
    </div>)}
  </div>
}

function CreateUserDialog({ twoFactor, onClose, onSaved }: { twoFactor: boolean; onClose: () => void; onSaved: () => void }) {
  const [values, setValues] = useState({ display_name: '', username: '', password: '', role: 'reader' as AccessRole, current_password: '', otp: '' })
  const [error, setError] = useState(''); const [saving, setSaving] = useState(false)
  const submit = async (event: React.FormEvent) => { event.preventDefault(); setSaving(true); setError(''); try { await api('/users', { method: 'POST', ...jsonBody(values) }); onSaved() } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo crear la cuenta') } finally { setSaving(false) } }
  return <Modal title="Nueva persona" description="La contraseña inicial deberá cambiarse en su primer acceso." onClose={onClose} size="large"><form className="modal-body form-stack" onSubmit={submit}>
    <div className="form-grid"><label className="field"><span>Nombre visible</span><input autoFocus value={values.display_name} onChange={event => setValues({ ...values, display_name: event.target.value })} required /></label><label className="field"><span>Usuario</span><input autoCapitalize="none" value={values.username} onChange={event => setValues({ ...values, username: event.target.value })} required /></label></div>
    <label className="field"><span>Contraseña inicial</span><input type="password" autoComplete="new-password" value={values.password} onChange={event => setValues({ ...values, password: event.target.value })} required /></label>
    <label className="field"><span>Nivel de acceso</span><select value={values.role} onChange={event => setValues({ ...values, role: event.target.value as AccessRole })}><RoleOptions /></select><small>{roleDescriptions[values.role]}</small></label>
    <ConfirmationFields password={values.current_password} setPassword={current_password => setValues({ ...values, current_password })} otp={values.otp} setOtp={otp => setValues({ ...values, otp })} twoFactor={twoFactor} />
    {error && <div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancelar</button><button className="button primary" disabled={saving}>{saving ? 'Creando…' : 'Crear cuenta'}</button></div>
  </form></Modal>
}

function EditUserDialog({ user, twoFactor, onClose, onSaved }: { user: ManagedUser; twoFactor: boolean; onClose: () => void; onSaved: () => void }) {
  const [username, setUsername] = useState(user.username); const [displayName, setDisplayName] = useState(user.display_name); const [role, setRole] = useState(user.role); const [status, setStatus] = useState(user.status); const [password, setPassword] = useState(''); const [otp, setOtp] = useState(''); const [error, setError] = useState(''); const [saving, setSaving] = useState(false)
  const submit = async (event: React.FormEvent) => { event.preventDefault(); setSaving(true); setError(''); try { await api(`/users/${user.id}`, { method: 'PATCH', ...jsonBody({ username, display_name: displayName, role, status, current_password: password, otp: otp || null }) }); onSaved() } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo actualizar la cuenta') } finally { setSaving(false) } }
  return <Modal title={`Gestionar a ${user.display_name}`} description={`Cuenta nominal @${user.username}`} onClose={onClose}><form className="modal-body form-stack" onSubmit={submit}>
    <div className="form-grid"><label className="field"><span>Nombre visible</span><input value={displayName} onChange={event => setDisplayName(event.target.value)} required /></label><label className="field"><span>Usuario</span><input autoCapitalize="none" value={username} onChange={event => setUsername(event.target.value)} required /></label></div>
    <label className="field"><span>Nivel de acceso</span><select value={role} onChange={event => setRole(event.target.value as AccessRole)}><RoleOptions /></select><small>{roleDescriptions[role]}</small></label>
    <label className="field"><span>Estado de la cuenta</span><select value={status} onChange={event => setStatus(event.target.value as 'active' | 'disabled')}><option value="active">Activa</option><option value="disabled">Desactivada</option></select></label>
    <ConfirmationFields password={password} setPassword={setPassword} otp={otp} setOtp={setOtp} twoFactor={twoFactor} />
    {error && <div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancelar</button><button className="button primary" disabled={saving}>{saving ? 'Guardando…' : 'Guardar acceso'}</button></div>
  </form></Modal>
}

function ResetUserDialog({ user, twoFactor, onClose, onSaved }: { user: ManagedUser; twoFactor: boolean; onClose: () => void; onSaved: () => void }) {
  const [newPassword, setNewPassword] = useState(''); const [password, setPassword] = useState(''); const [otp, setOtp] = useState(''); const [error, setError] = useState(''); const [saving, setSaving] = useState(false)
  const submit = async (event: React.FormEvent) => { event.preventDefault(); setSaving(true); setError(''); try { await api(`/users/${user.id}/reset-password`, { method: 'POST', ...jsonBody({ new_password: newPassword, current_password: password, otp: otp || null }) }); onSaved() } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo restablecer la contraseña') } finally { setSaving(false) } }
  return <Modal title="Restablecer contraseña" description={`${user.display_name} deberá cambiarla en su próximo acceso.`} onClose={onClose}><form className="modal-body form-stack" onSubmit={submit}>
    <label className="field"><span>Nueva contraseña temporal</span><input autoFocus type="password" autoComplete="new-password" value={newPassword} onChange={event => setNewPassword(event.target.value)} required /></label>
    <ConfirmationFields password={password} setPassword={setPassword} otp={otp} setOtp={setOtp} twoFactor={twoFactor} />
    {error && <div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancelar</button><button className="button primary" disabled={saving}>{saving ? 'Restableciendo…' : 'Restablecer'}</button></div>
  </form></Modal>
}

function CreateApiDialog({ twoFactor, onClose, onSaved }: { twoFactor: boolean; onClose: () => void; onSaved: (name: string, token: string) => void }) {
  const [values, setValues] = useState({ name: '', description: '', role: 'reader' as AccessRole, expires_at: '', current_password: '', otp: '' }); const [error, setError] = useState(''); const [saving, setSaving] = useState(false)
  const submit = async (event: React.FormEvent) => { event.preventDefault(); setSaving(true); setError(''); try { const result = await api<{ item: ApiClient; token: string }>('/users/api-clients', { method: 'POST', ...jsonBody({ ...values, expires_at: values.expires_at ? new Date(`${values.expires_at}T23:59:59Z`).toISOString() : null }) }); onSaved(result.item.name, result.token) } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo registrar la aplicación') } finally { setSaving(false) } }
  return <Modal title="Registrar aplicación API" description="El token se mostrará una sola vez al completar el alta." onClose={onClose} size="large"><form className="modal-body form-stack" onSubmit={submit}>
    <label className="field"><span>Nombre de la aplicación</span><input autoFocus value={values.name} onChange={event => setValues({ ...values, name: event.target.value })} required /></label>
    <label className="field"><span>Descripción</span><textarea rows={3} value={values.description} onChange={event => setValues({ ...values, description: event.target.value })} /></label>
    <div className="form-grid"><label className="field"><span>Nivel de acceso</span><select value={values.role} onChange={event => setValues({ ...values, role: event.target.value as AccessRole })}><RoleOptions /></select></label><label className="field"><span>Caducidad <small>Opcional</small></span><input type="date" value={values.expires_at} onChange={event => setValues({ ...values, expires_at: event.target.value })} /></label></div>
    <p className="field-help">{roleDescriptions[values.role]}</p><ConfirmationFields password={values.current_password} setPassword={current_password => setValues({ ...values, current_password })} otp={values.otp} setOtp={otp => setValues({ ...values, otp })} twoFactor={twoFactor} />
    {error && <div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancelar</button><button className="button primary" disabled={saving}>{saving ? 'Registrando…' : 'Crear y emitir token'}</button></div>
  </form></Modal>
}

function EditApiDialog({ client, twoFactor, onClose, onSaved }: { client: ApiClient; twoFactor: boolean; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(client.name); const [role, setRole] = useState(client.role); const [status, setStatus] = useState(client.status === 'revoked' ? 'disabled' : client.status); const [description, setDescription] = useState(client.description); const [expiresAt, setExpiresAt] = useState(client.expires_at?.slice(0, 10) || ''); const [password, setPassword] = useState(''); const [otp, setOtp] = useState(''); const [error, setError] = useState(''); const [saving, setSaving] = useState(false)
  const submit = async (event: React.FormEvent) => { event.preventDefault(); setSaving(true); setError(''); try { await api(`/users/api-clients/${client.id}`, { method: 'PATCH', ...jsonBody({ name, description, role, status, expires_at: expiresAt ? new Date(`${expiresAt}T23:59:59Z`).toISOString() : null, current_password: password, otp: otp || null }) }); onSaved() } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo actualizar el acceso') } finally { setSaving(false) } }
  return <Modal title={`Gestionar ${client.name}`} description={`Token ${client.token_prefix}…`} onClose={onClose}><form className="modal-body form-stack" onSubmit={submit}>
    <label className="field"><span>Nombre de la aplicación</span><input value={name} onChange={event => setName(event.target.value)} required /></label><label className="field"><span>Descripción</span><textarea rows={3} value={description} onChange={event => setDescription(event.target.value)} /></label><div className="form-grid"><label className="field"><span>Nivel de acceso</span><select value={role} onChange={event => setRole(event.target.value as AccessRole)}><RoleOptions /></select></label><label className="field"><span>Caducidad <small>Opcional</small></span><input type="date" value={expiresAt} onChange={event => setExpiresAt(event.target.value)} /></label></div><p className="field-help">{roleDescriptions[role]}</p>
    <label className="field"><span>Estado</span><select value={status} onChange={event => setStatus(event.target.value as 'active' | 'disabled')} disabled={client.status === 'revoked'}><option value="active">Activo</option><option value="disabled">Desactivado</option></select></label>{client.status === 'revoked' && <p className="field-help danger-text">Un token revocado no puede reactivarse. Rótalo para emitir uno nuevo.</p>}
    <ConfirmationFields password={password} setPassword={setPassword} otp={otp} setOtp={setOtp} twoFactor={twoFactor} />{error && <div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancelar</button><button className="button primary" disabled={saving || client.status === 'revoked'}>{saving ? 'Guardando…' : 'Guardar acceso'}</button></div>
  </form></Modal>
}

function ApiTokenActionDialog({ action, client, twoFactor, onClose, onSaved }: { action: 'rotate' | 'revoke'; client: ApiClient; twoFactor: boolean; onClose: () => void; onSaved: (token?: string) => void }) {
  const [password, setPassword] = useState(''); const [otp, setOtp] = useState(''); const [error, setError] = useState(''); const [saving, setSaving] = useState(false)
  const submit = async (event: React.FormEvent) => { event.preventDefault(); setSaving(true); setError(''); try { const result = await api<{ token?: string }>(`/users/api-clients/${client.id}/${action}`, { method: 'POST', ...jsonBody({ current_password: password, otp: otp || null }) }); onSaved(result.token) } catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo completar la operación') } finally { setSaving(false) } }
  return <Modal title={action === 'rotate' ? 'Rotar token API' : 'Revocar token API'} description={action === 'rotate' ? `El token actual de ${client.name} dejará de funcionar inmediatamente.` : `${client.name} perderá el acceso de forma irreversible.`} onClose={onClose}><form className="modal-body form-stack" onSubmit={submit}>
    <ConfirmationFields password={password} setPassword={setPassword} otp={otp} setOtp={setOtp} twoFactor={twoFactor} />{error && <div className="form-error">{error}</div>}<div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancelar</button><button className={`button ${action === 'revoke' ? 'danger-button' : 'primary'}`} disabled={saving}>{saving ? 'Procesando…' : action === 'rotate' ? 'Rotar y mostrar token' : 'Revocar acceso'}</button></div>
  </form></Modal>
}

function TokenReveal({ value, onClose }: { value: { name: string; token: string }; onClose: () => void }) {
  const [copied, setCopied] = useState(false)
  const [notice, setNotice] = useState<{ id: number; tone: ToastTone; message: string } | null>(null)
  const showNotice = (tone: ToastTone, message: string) => {
    setNotice(current => ({ id: (current?.id ?? 0) + 1, tone, message }))
  }
  const copy = async () => {
    try {
      await copyText(value.token)
      setCopied(true)
      showNotice('success', 'Token copiado')
    } catch {
      setCopied(false)
      showNotice('error', 'No se pudo copiar el token')
    }
  }
  return <>
    <Modal title="Token API emitido" description={`Credencial privada para ${value.name}`} onClose={onClose}><div className="modal-body form-stack">
      <div className="token-warning"><KeyRound size={21} /><div><strong>Guárdalo ahora</strong><p>No volverá a mostrarse y no puede recuperarse. Si se pierde, tendrás que rotarlo.</p></div></div>
      <div className="token-reveal"><code>{value.token}</code><button type="button" className="button secondary" onClick={() => void copy()}>{copied ? <Check size={17} /> : <Copy size={17} />}{copied ? 'Copiado' : 'Copiar'}</button></div>
      <div className="modal-actions"><button type="button" className="button primary" onClick={onClose}>He guardado el token</button></div>
    </div></Modal>
    {notice && <Toast key={notice.id} message={notice.message} tone={notice.tone} onDismiss={() => setNotice(null)} />}
  </>
}
