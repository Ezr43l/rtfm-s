import { ArrowRight, KeyRound, ShieldCheck, Smartphone } from 'lucide-react'
import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ApiError } from '../lib/api'

export function LoginPage() {
  const { session, login } = useAuth()
  const [actor, setActor] = useState('')
  const [credential, setCredential] = useState('')
  const [otp, setOtp] = useState('')
  const [requiresSecondFactor, setRequiresSecondFactor] = useState(false)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  if (session) return <Navigate to="/dashboard" replace />

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await login(actor, credential, otp)
      const destination = (location.state as { from?: string } | null)?.from || '/dashboard'
      navigate(destination, { replace: true })
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === 'TWO_FACTOR_REQUIRED') {
        setRequiresSecondFactor(true)
        setError('')
      } else {
        setError(caught instanceof ApiError ? caught.message : 'No se pudo iniciar la sesión')
      }
    } finally { setSubmitting(false) }
  }

  return <main className="login-page">
    <section className="login-intro">
      <img src="/icono.svg" alt="" />
      <span className="eyebrow">CONOCIMIENTO OPERATIVO</span>
      <h1>Toda la infraestructura,<br />en un único lugar.</h1>
      <p>Documentación privada, versionada y preparada para sobrevivir a la caída de cualquier nodo.</p>
      <div className="login-feature"><ShieldCheck size={21} /><span>Acceso protegido y operaciones auditadas</span></div>
    </section>
    <section className="login-panel">
      <form className="login-form" onSubmit={submit}>
        <div className="login-symbol"><KeyRound size={23} /></div>
        <span className="eyebrow">ACCESO PRIVADO</span>
        <h2>Entrar en RTFM</h2>
        <p>Accede con tu usuario, contraseña y segundo factor cuando esté activado.</p>
        <label className="field"><span>Usuario</span><input autoFocus value={actor} onChange={event => { setActor(event.target.value); setRequiresSecondFactor(false) }} required autoComplete="username" /></label>
        <label className="field"><span>Contraseña</span><input type="password" value={credential} onChange={event => { setCredential(event.target.value); setRequiresSecondFactor(false) }} required autoComplete="current-password" /></label>
        {requiresSecondFactor && <label className="field two-factor-field"><span><Smartphone size={16} /> Código 2FA</span><input value={otp} onChange={event => setOtp(event.target.value)} required autoFocus inputMode="numeric" autoComplete="one-time-code" placeholder="6 dígitos o código de recuperación" /></label>}
        {error && <div className="form-error">{error}</div>}
        <button className="button primary wide" disabled={submitting}>{submitting ? 'Comprobando…' : <>{requiresSecondFactor ? 'Verificar y acceder' : 'Acceder'} <ArrowRight size={18} /></>}</button>
      </form>
    </section>
  </main>
}
