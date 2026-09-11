import {
  Check, Clipboard, Download, KeyRound, LoaderCircle, LockKeyhole, ShieldCheck,
  ShieldOff, Smartphone, UserRound,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { ErrorState, LoadingState } from '../components/Feedback'
import { useAuth } from '../context/AuthContext'
import { ContentCard } from '../layout/AppShell'
import { api, ApiError, formatDate, jsonBody } from '../lib/api'
import type { UserProfile } from '../types'

interface TwoFactorSetupResponse {
  secret: string
  otpauth_uri: string
  qr_data_url: string
  issuer: string
}

interface SecurityResponse {
  profile: UserProfile
  recovery_codes?: string[]
}

function messageOf(error: unknown) {
  return error instanceof ApiError ? error.message : 'No se ha podido completar la operación'
}

export function ProfilePage() {
  const { refresh } = useAuth()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [profilePassword, setProfilePassword] = useState('')

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordOtp, setPasswordOtp] = useState('')

  const [setupPassword, setSetupPassword] = useState('')
  const [setupCode, setSetupCode] = useState('')
  const [setup, setSetup] = useState<TwoFactorSetupResponse | null>(null)
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([])

  const [disablePassword, setDisablePassword] = useState('')
  const [disableCode, setDisableCode] = useState('')
  const [regeneratePassword, setRegeneratePassword] = useState('')
  const [regenerateCode, setRegenerateCode] = useState('')

  const applyProfile = (value: UserProfile) => {
    setProfile(value)
    setUsername(value.username)
    setDisplayName(value.display_name)
  }

  const load = async () => {
    setLoading(true)
    setError('')
    try { applyProfile(await api<UserProfile>('/profile')) }
    catch (caught) { setError(messageOf(caught)) }
    finally { setLoading(false) }
  }

  useEffect(() => { void load() }, [])

  const run = async (name: string, action: () => Promise<void>) => {
    setBusy(name)
    setError('')
    setNotice('')
    try { await action() }
    catch (caught) { setError(messageOf(caught)) }
    finally { setBusy('') }
  }

  const saveProfile = (event: React.FormEvent) => {
    event.preventDefault()
    void run('profile', async () => {
      const updated = await api<UserProfile>('/profile', {
        method: 'PATCH',
        ...jsonBody({ username, display_name: displayName, current_password: profilePassword || null }),
      })
      applyProfile(updated)
      setProfilePassword('')
      await refresh()
      setNotice('El perfil se ha actualizado.')
    })
  }

  const changePassword = (event: React.FormEvent) => {
    event.preventDefault()
    if (newPassword !== confirmPassword) { setError('La confirmación no coincide con la nueva contraseña.'); return }
    void run('password', async () => {
      const result = await api<SecurityResponse>('/profile/password', {
        method: 'POST',
        ...jsonBody({ current_password: currentPassword, new_password: newPassword, otp: passwordOtp || null }),
      })
      applyProfile(result.profile)
      setCurrentPassword(''); setNewPassword(''); setConfirmPassword(''); setPasswordOtp('')
      await refresh()
      setNotice('La contraseña se ha cambiado y las sesiones anteriores han quedado invalidadas.')
    })
  }

  const beginTwoFactor = (event: React.FormEvent) => {
    event.preventDefault()
    void run('2fa-setup', async () => {
      const result = await api<TwoFactorSetupResponse>('/profile/2fa/setup', {
        method: 'POST', ...jsonBody({ current_password: setupPassword }),
      })
      setSetup(result)
      setSetupCode('')
    })
  }

  const cancelTwoFactor = () => {
    void run('2fa-cancel', async () => {
      await api('/profile/2fa/setup', { method: 'DELETE' })
      setSetup(null); setSetupPassword(''); setSetupCode('')
      setNotice('La configuración pendiente se ha descartado.')
    })
  }

  const enableTwoFactor = (event: React.FormEvent) => {
    event.preventDefault()
    void run('2fa-enable', async () => {
      const result = await api<SecurityResponse>('/profile/2fa/enable', {
        method: 'POST', ...jsonBody({ code: setupCode }),
      })
      applyProfile(result.profile)
      setRecoveryCodes(result.recovery_codes || [])
      setSetup(null); setSetupPassword(''); setSetupCode('')
      await refresh()
      setNotice('La autenticación en dos pasos está activa. Guarda ahora los códigos de recuperación.')
    })
  }

  const disableTwoFactor = (event: React.FormEvent) => {
    event.preventDefault()
    void run('2fa-disable', async () => {
      const result = await api<SecurityResponse>('/profile/2fa/disable', {
        method: 'POST', ...jsonBody({ current_password: disablePassword, code: disableCode }),
      })
      applyProfile(result.profile)
      setDisablePassword(''); setDisableCode(''); setRecoveryCodes([])
      await refresh()
      setNotice('La autenticación en dos pasos se ha desactivado.')
    })
  }

  const regenerateRecoveryCodes = (event: React.FormEvent) => {
    event.preventDefault()
    void run('recovery', async () => {
      const result = await api<SecurityResponse>('/profile/2fa/recovery-codes', {
        method: 'POST', ...jsonBody({ current_password: regeneratePassword, code: regenerateCode }),
      })
      applyProfile(result.profile)
      setRecoveryCodes(result.recovery_codes || [])
      setRegeneratePassword(''); setRegenerateCode('')
      setNotice('Los códigos anteriores han sido anulados. Guarda el nuevo juego.')
    })
  }

  const recoveryText = recoveryCodes.join('\n')
  const copyRecoveryCodes = async () => { await navigator.clipboard.writeText(recoveryText); setNotice('Códigos copiados al portapapeles.') }
  const downloadRecoveryCodes = () => {
    const blob = new Blob([`RTFM · códigos de recuperación\n\n${recoveryText}\n`], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a'); link.href = url; link.download = 'rtfm-codigos-recuperacion.txt'; link.click()
    URL.revokeObjectURL(url)
  }

  if (loading) return <LoadingState label="Cargando el perfil…" />
  if (!profile) return <ErrorState message={error || 'No se ha podido cargar el perfil'} retry={() => void load()} />

  return <>
    <header className="page-header">
      <div><span className="eyebrow">CUENTA Y SEGURIDAD</span><h1>Mi perfil</h1><p>Gestiona tu identidad, la contraseña y la autenticación en dos pasos.</p></div>
      <span className={`security-pill ${profile.two_factor_enabled ? 'enabled' : ''}`}><ShieldCheck size={17} /> 2FA {profile.two_factor_enabled ? 'activado' : 'desactivado'}</span>
    </header>

    {profile.password_change_required && <div className="security-banner warning"><KeyRound size={21} /><div><strong>Cambia la contraseña inicial</strong><p>La cuenta acaba de migrarse desde la credencial provisional. Elige una contraseña personal para separarla del token de API.</p></div></div>}
    {error && <div className="security-banner error"><ShieldOff size={21} /><div><strong>No se ha podido guardar</strong><p>{error}</p></div></div>}
    {notice && <div className="security-banner success"><Check size={21} /><div><strong>Operación completada</strong><p>{notice}</p></div></div>}

    <div className="profile-grid">
      <ContentCard className="profile-card">
        <div className="profile-card-heading"><span className="settings-icon"><UserRound size={21} /></span><div><h2>Identidad</h2><p>El nombre visible aparece en la interfaz; el usuario sirve para iniciar sesión y firmar operaciones.</p></div></div>
        <form className="profile-form" onSubmit={saveProfile}>
          <label className="field"><span>Nombre visible</span><input value={displayName} onChange={event => setDisplayName(event.target.value)} maxLength={120} required autoComplete="name" /></label>
          <label className="field"><span>Nombre de usuario</span><input value={username} onChange={event => setUsername(event.target.value)} minLength={3} maxLength={64} required autoComplete="username" /></label>
          {username !== profile.username && <label className="field"><span>Contraseña actual <small>necesaria para cambiar el usuario</small></span><input type="password" value={profilePassword} onChange={event => setProfilePassword(event.target.value)} required autoComplete="current-password" /></label>}
          <div className="profile-meta"><span>Rol <strong>{profile.role}</strong></span><span>Actualizado <strong>{formatDate(profile.updated_at)}</strong></span></div>
          <button className="button primary" disabled={busy === 'profile'}>{busy === 'profile' ? <><LoaderCircle className="spin" size={17} /> Guardando…</> : 'Guardar perfil'}</button>
        </form>
      </ContentCard>

      <ContentCard className="profile-card">
        <div className="profile-card-heading"><span className="settings-icon"><LockKeyhole size={21} /></span><div><h2>Contraseña</h2><p>Al cambiarla se invalidan automáticamente las demás sesiones abiertas.</p></div></div>
        <form className="profile-form" onSubmit={changePassword}>
          <label className="field"><span>Contraseña actual</span><input type="password" value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} required autoComplete="current-password" /></label>
          <label className="field"><span>Nueva contraseña</span><input type="password" value={newPassword} onChange={event => setNewPassword(event.target.value)} minLength={profile.password_policy.minimum_length} required autoComplete="new-password" /><small>Mínimo {profile.password_policy.minimum_length} caracteres. Se admite una frase larga.</small></label>
          <label className="field"><span>Confirmar contraseña</span><input type="password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} required autoComplete="new-password" /></label>
          {profile.two_factor_enabled && <label className="field"><span>Código 2FA</span><input value={passwordOtp} onChange={event => setPasswordOtp(event.target.value)} required inputMode="numeric" autoComplete="one-time-code" /></label>}
          <button className="button primary" disabled={busy === 'password'}>{busy === 'password' ? <><LoaderCircle className="spin" size={17} /> Cambiando…</> : 'Cambiar contraseña'}</button>
        </form>
      </ContentCard>
    </div>

    <ContentCard className="profile-card two-factor-card">
      <div className="profile-card-heading"><span className="settings-icon"><Smartphone size={21} /></span><div><h2>Autenticación en dos pasos</h2><p>Compatible con Aegis, 2FAS, Google Authenticator, Microsoft Authenticator y cualquier aplicación TOTP estándar.</p></div></div>

      {!profile.two_factor_enabled && !setup && <form className="profile-form compact-form" onSubmit={beginTwoFactor}>
        <label className="field"><span>Confirma tu contraseña para empezar</span><input type="password" value={setupPassword} onChange={event => setSetupPassword(event.target.value)} required autoComplete="current-password" /></label>
        <button className="button primary" disabled={busy === '2fa-setup'}>{busy === '2fa-setup' ? 'Preparando…' : 'Configurar 2FA'}</button>
      </form>}

      {!profile.two_factor_enabled && setup && <div className="two-factor-setup">
        <div className="qr-panel"><img src={setup.qr_data_url} alt="Código QR para configurar TOTP" /><span>Escanea con tu aplicación autenticadora</span></div>
        <form className="profile-form" onSubmit={enableTwoFactor}>
          <div><span className="step-label">1 · ESCANEA EL QR</span><p>La cuenta aparecerá como <strong>{setup.issuer}</strong>. Si no puedes escanear, introduce esta clave manualmente:</p><code className="totp-secret">{setup.secret}</code></div>
          <label className="field"><span>2 · Introduce el código de 6 dígitos</span><input value={setupCode} onChange={event => setSetupCode(event.target.value)} required inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" placeholder="000000" /></label>
          <div className="form-actions"><button type="button" className="button secondary" onClick={cancelTwoFactor}>Cancelar</button><button className="button primary" disabled={busy === '2fa-enable'}>{busy === '2fa-enable' ? 'Verificando…' : 'Verificar y activar'}</button></div>
        </form>
      </div>}

      {profile.two_factor_enabled && <div className="two-factor-enabled-grid">
        <div className="two-factor-status"><span className="large-status ok"><ShieldCheck size={23} /></span><div><strong>Segundo factor activo</strong><p>Quedan {profile.recovery_codes_remaining} códigos de recuperación sin usar.</p></div></div>
        <form className="profile-form" onSubmit={disableTwoFactor}>
          <h3>Desactivar 2FA</h3>
          <label className="field"><span>Contraseña actual</span><input type="password" value={disablePassword} onChange={event => setDisablePassword(event.target.value)} required autoComplete="current-password" /></label>
          <label className="field"><span>Código 2FA o de recuperación</span><input value={disableCode} onChange={event => setDisableCode(event.target.value)} required autoComplete="one-time-code" /></label>
          <button className="button secondary danger-text" disabled={busy === '2fa-disable'}>Desactivar autenticación en dos pasos</button>
        </form>
        <form className="profile-form" onSubmit={regenerateRecoveryCodes}>
          <h3>Renovar códigos de recuperación</h3>
          <label className="field"><span>Contraseña actual</span><input type="password" value={regeneratePassword} onChange={event => setRegeneratePassword(event.target.value)} required autoComplete="current-password" /></label>
          <label className="field"><span>Código 2FA</span><input value={regenerateCode} onChange={event => setRegenerateCode(event.target.value)} required autoComplete="one-time-code" /></label>
          <button className="button secondary" disabled={busy === 'recovery'}>Generar códigos nuevos</button>
        </form>
      </div>}
    </ContentCard>

    {recoveryCodes.length > 0 && <ContentCard className="recovery-card">
      <div><span className="eyebrow">GUARDAR AHORA</span><h2>Códigos de recuperación</h2><p>Cada código permite entrar una sola vez si pierdes el segundo factor. No volverán a mostrarse.</p></div>
      <div className="recovery-codes">{recoveryCodes.map(code => <code key={code}>{code}</code>)}</div>
      <div className="form-actions"><button className="button secondary" onClick={() => void copyRecoveryCodes()}><Clipboard size={17} /> Copiar</button><button className="button primary" onClick={downloadRecoveryCodes}><Download size={17} /> Descargar TXT</button></div>
    </ContentCard>}
  </>
}
