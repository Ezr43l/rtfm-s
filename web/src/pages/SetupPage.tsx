import { CheckCircle2, ServerCog } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { api, jsonBody } from '../lib/api'

type SetupResult = { ok: boolean; restarting: boolean; enrollment_code: string }

function peersFromText(value: string) {
  return value.split(/\r?\n/).map(line => line.trim()).filter(Boolean).map(line => {
    const parts = line.split('|').map(part => part.trim())
    if (parts.length !== 2 || !parts[0] || !parts[1]) throw new Error(`Réplica no válida: ${line}`)
    return { name: parts[0], url: parts[1] }
  })
}

function portsFromText(value: string) {
  return value.split(',').map(item => item.trim()).filter(Boolean).map(item => {
    const port = Number(item)
    if (!Number.isInteger(port)) throw new Error(`Puerto no válido: ${item}`)
    return port
  })
}

export function SetupPage() {
  const [node, setNode] = useState('')
  const [roleMode, setRoleMode] = useState('active')
  const [scheme, setScheme] = useState('http')
  const [proxies, setProxies] = useState('127.0.0.1')
  const [floatingIp, setFloatingIp] = useState('')
  const [floatingUrl, setFloatingUrl] = useState('')
  const [secureCookie, setSecureCookie] = useState(false)
  const [keepUrl, setKeepUrl] = useState('')
  const [keepKey, setKeepKey] = useState('')
  const [keepService, setKeepService] = useState('rtfm')
  const [keepDescription, setKeepDescription] = useState('RTFM')
  const [claimId, setClaimId] = useState('')
  const [healthPath, setHealthPath] = useState('/api/health')
  const [servicePorts, setServicePorts] = useState('')
  const [keepTimeout, setKeepTimeout] = useState(5)
  const [keepInsecure, setKeepInsecure] = useState(false)
  const [keepCa, setKeepCa] = useState('')
  const [peers, setPeers] = useState('')
  const [replicationInsecure, setReplicationInsecure] = useState(false)
  const [replicationCa, setReplicationCa] = useState('')
  const [maxReplication, setMaxReplication] = useState(512)
  const [retention, setRetention] = useState(90)
  const [syncInterval, setSyncInterval] = useState(300)
  const [maxImage, setMaxImage] = useState(10)
  const [sessionHours, setSessionHours] = useState(12)
  const [loginAttempts, setLoginAttempts] = useState(5)
  const [loginWindow, setLoginWindow] = useState(300)
  const [passwordMin, setPasswordMin] = useState(12)
  const [issuer, setIssuer] = useState('RTFM')
  const [gitEnabled, setGitEnabled] = useState(true)
  const [gitName, setGitName] = useState('RTFM')
  const [gitEmail, setGitEmail] = useState('rtfm@localhost')
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [enrollment, setEnrollment] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<SetupResult | null>(null)
  const joining = Boolean(enrollment.trim())

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const payload = {
        node: node.trim(), role_mode: roleMode,
        public: {
          scheme, forwarded_allow_ips: proxies.trim(), floating_ip: floatingIp.trim(),
          floating_url: floatingUrl.trim(), session_cookie_secure: secureCookie,
        },
        keepalived: {
          url: keepUrl.trim(), api_key: keepKey.trim(), service: keepService.trim(),
          description: keepDescription.trim(), claim_id: claimId.trim(),
          health_path: healthPath.trim(), service_ports: portsFromText(servicePorts),
          timeout_seconds: keepTimeout, allow_insecure_http: keepInsecure, ca_pem: keepCa.trim(),
        },
        replication: {
          peers: peersFromText(peers), allow_insecure_http: replicationInsecure,
          ca_pem: replicationCa.trim(), max_mb: maxReplication,
        },
        policy: {
          retention_days: retention, sync_interval_seconds: syncInterval,
          max_image_size_mb: maxImage, session_hours: sessionHours,
          login_max_attempts: loginAttempts, login_window_seconds: loginWindow,
          password_min_length: passwordMin, totp_issuer: issuer.trim(),
        },
        git: { enabled: gitEnabled, author_name: gitName.trim(), author_email: gitEmail.trim() },
        owner: joining ? null : {
          username: username.trim(), display_name: displayName.trim(), password,
        },
        enrollment_code: enrollment.trim(),
      }
      setResult(await api<SetupResult>('/setup', { method: 'POST', ...jsonBody(payload) }))
      setPassword(''); setKeepKey('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'No se pudo guardar la configuración')
    } finally { setBusy(false) }
  }

  if (result) return <main className="setup-page"><section className="setup-done">
    <CheckCircle2 size={42} /><span className="eyebrow">CONFIGURACIÓN GUARDADA</span>
    <h1>RTFM está preparado</h1>
    {result.enrollment_code && <><p>Guarda este código si vas a añadir otros nodos. Contiene credenciales privadas y sólo se muestra ahora.</p><textarea readOnly rows={6} value={result.enrollment_code} /><button className="button secondary" onClick={() => void navigator.clipboard.writeText(result.enrollment_code)}>Copiar código de incorporación</button></>}
    {!result.enrollment_code && <p>Este nodo recibirá las cuentas desde el nodo activo mediante la réplica.</p>}
    <p>{result.restarting ? 'El servicio se está reiniciando con la nueva configuración.' : 'Reinicia el contenedor para aplicar la configuración.'}</p>
    <button className="button primary" onClick={() => window.location.reload()}>Continuar</button>
  </section></main>

  return <main className="setup-page"><form className="setup-shell" onSubmit={event => void submit(event)}>
    <header className="setup-heading"><div className="login-symbol"><ServerCog size={24} /></div><span className="eyebrow">PRIMER ARRANQUE</span><h1>Configurar RTFM</h1><p>Estos datos se guardan dentro del volumen de RTFM, no en la plantilla de Unraid.</p></header>

    <section className="setup-section"><h2>Instancia</h2><div className="setup-grid">
      <label className="field"><span>Nombre del nodo</span><input required value={node} onChange={e => setNode(e.target.value)} placeholder="node-a" /></label>
      <label className="field"><span>Modo</span><select value={roleMode} onChange={e => setRoleMode(e.target.value)}><option value="active">Activo fijo · un solo nodo</option><option value="auto">Automático · IP flotante</option><option value="passive">Pasivo fijo · diagnóstico</option><option value="unknown">Bloqueado</option></select></label>
      <label className="field"><span>Esquema público</span><select value={scheme} onChange={e => setScheme(e.target.value)}><option value="http">HTTP</option><option value="https">HTTPS</option></select></label>
      <label className="field"><span>Proxies de confianza</span><input required value={proxies} onChange={e => setProxies(e.target.value)} /></label>
      <label className="field"><span>IP flotante manual</span><input value={floatingIp} onChange={e => setFloatingIp(e.target.value)} placeholder="Opcional" /></label>
      <label className="field"><span>URL pública flotante</span><input value={floatingUrl} onChange={e => setFloatingUrl(e.target.value)} placeholder="Opcional" /></label>
    </div><label className="setup-check"><input type="checkbox" checked={secureCookie} onChange={e => setSecureCookie(e.target.checked)} /> Cookie de sesión Secure; sólo si todo el acceso usa HTTPS</label></section>

    <section className="setup-section"><h2>Keepalived <small>opcional</small></h2><p>Configúralo sólo si RTFM debe reservar una dirección flotante. En una instalación independiente puedes dejar los dos campos vacíos.</p>
      <ol className="configuration-steps">
        <li>En Keepalived abre <strong>Cuenta → Claves API</strong> y crea una clave para RTFM con el permiso <code>claims:write</code>.</li>
        <li>Introduce la dirección del <strong>primer nodo de Keepalived</strong>, que es su coordinador o escritor.</li>
        <li>RTFM generará automáticamente la reclamación y usará su propio puerto y ruta de salud.</li>
      </ol><div className="setup-grid aligned-fields">
        <label className="field"><span>Dirección del Keepalived coordinador</span><input value={keepUrl} onChange={e => setKeepUrl(e.target.value)} placeholder="Ej. http://192.0.2.10:6060" /><small>URL base con protocolo y puerto, sin añadir <code>/api/claims</code>.</small></label>
        <label className="field"><span>Clave API para RTFM</span><input type="password" value={keepKey} onChange={e => setKeepKey(e.target.value)} placeholder="Ej. fip_…" autoComplete="new-password" /><small>La clave se muestra una sola vez al crearla en Keepalived.</small></label>
      </div><label className="setup-check configuration-check"><input type="checkbox" checked={keepInsecure} onChange={e => setKeepInsecure(e.target.checked)} /><span><strong>Permitir HTTP dentro de la red privada</strong><small>Actívalo sólo si la dirección anterior usa <code>http://</code> dentro de una LAN o VPN de confianza.</small></span></label>
      <details className="configuration-advanced"><summary><span>Ajustes avanzados de la reclamación</span><small>Los valores predeterminados son correctos para una instalación normal.</small></summary><div className="setup-grid aligned-fields">
        <label className="field"><span>Nombre técnico del servicio</span><input value={keepService} onChange={e => setKeepService(e.target.value)} placeholder="rtfm" /><small>Debe ser el mismo en todos los nodos de RTFM.</small></label>
        <label className="field"><span>Descripción visible en Keepalived</span><input value={keepDescription} onChange={e => setKeepDescription(e.target.value)} placeholder="RTFM" /><small>Texto que identificará la aplicación en el panel.</small></label>
        <label className="field"><span>Identificador estable de reclamación</span><input value={claimId} onChange={e => setClaimId(e.target.value)} placeholder="RTFM lo genera automáticamente" /><small>Déjalo vacío en el primer nodo. Los nodos adicionales lo reciben mediante el código de incorporación.</small></label>
        <label className="field"><span>Ruta de salud de RTFM</span><input value={healthPath} onChange={e => setHealthPath(e.target.value)} placeholder="/api/health" /><small>Keepalived la consulta para decidir si el nodo puede sostener la IP.</small></label>
        <label className="field"><span>Puertos públicos adicionales</span><input value={servicePorts} onChange={e => setServicePorts(e.target.value)} placeholder="Ej. 443,8443" /><small>El puerto propio de RTFM ya se incluye automáticamente.</small></label>
        <label className="field"><span>Espera máxima de la API</span><input type="number" min="1" max="30" value={keepTimeout} onChange={e => setKeepTimeout(Number(e.target.value))} /><small>Segundos que RTFM espera una respuesta.</small></label>
      </div><label className="field"><span>CA privada de Keepalived en formato PEM</span><textarea rows={3} value={keepCa} onChange={e => setKeepCa(e.target.value)} placeholder="Sólo para HTTPS con una autoridad certificadora privada" /><small>No es necesaria con HTTP ni con certificados HTTPS reconocidos públicamente.</small></label></details>
    </section>

    <section className="setup-section"><h2>Réplica entre nodos RTFM <small>opcional</small></h2><div className="configuration-guidance"><strong>Indica únicamente los otros nodos.</strong><span>Escribe uno por línea como <code>nombre | URL directa</code>. Usa la dirección propia de cada servidor, no la IP flotante. Déjalo vacío si sólo instalarás un nodo.</span></div><label className="field"><span>Otros nodos RTFM</span><textarea rows={4} value={peers} onChange={e => setPeers(e.target.value)} placeholder={'Ej. node-b | http://192.0.2.21:7400\nEj. node-c | http://192.0.2.22:7400'} /><small>Las credenciales compartidas y las cuentas se incorporan con el código generado por el primer nodo.</small></label><label className="field configuration-short-field"><span>Tamaño máximo de una réplica</span><input type="number" min="1" max="4096" value={maxReplication} onChange={e => setMaxReplication(Number(e.target.value))} /><small>Límite en MB para rechazar paquetes inesperadamente grandes.</small></label><label className="setup-check configuration-check"><input type="checkbox" checked={replicationInsecure} onChange={e => setReplicationInsecure(e.target.checked)} /><span><strong>Permitir réplica HTTP dentro de la red privada</strong><small>Actívalo sólo si las URL anteriores usan <code>http://</code> dentro de una LAN o VPN de confianza.</small></span></label><details className="configuration-advanced"><summary><span>Certificado avanzado para la réplica</span><small>Sólo es necesario con HTTPS y una autoridad certificadora privada.</small></summary><label className="field"><span>CA privada de réplica en formato PEM</span><textarea rows={3} value={replicationCa} onChange={e => setReplicationCa(e.target.value)} placeholder="-----BEGIN CERTIFICATE-----" /></label></details></section>

    <section className="setup-section"><h2>Políticas</h2><div className="setup-grid compact">
      <label className="field"><span>Retención del vault (días)</span><input type="number" min="1" value={retention} onChange={e => setRetention(Number(e.target.value))} /></label>
      <label className="field"><span>Sincronización (segundos)</span><input type="number" min="30" value={syncInterval} onChange={e => setSyncInterval(Number(e.target.value))} /></label>
      <label className="field"><span>Imagen máxima (MB)</span><input type="number" min="1" max="100" value={maxImage} onChange={e => setMaxImage(Number(e.target.value))} /></label>
      <label className="field"><span>Sesión (horas)</span><input type="number" min="1" value={sessionHours} onChange={e => setSessionHours(Number(e.target.value))} /></label>
      <label className="field"><span>Intentos de login</span><input type="number" min="3" max="50" value={loginAttempts} onChange={e => setLoginAttempts(Number(e.target.value))} /></label>
      <label className="field"><span>Ventana de login (s)</span><input type="number" min="30" max="3600" value={loginWindow} onChange={e => setLoginWindow(Number(e.target.value))} /></label>
      <label className="field"><span>Contraseña mínima</span><input type="number" min="12" max="256" value={passwordMin} onChange={e => setPasswordMin(Number(e.target.value))} /></label>
      <label className="field"><span>Nombre para 2FA</span><input value={issuer} onChange={e => setIssuer(e.target.value)} /></label>
    </div></section>

    <section className="setup-section"><h2>Historial Git</h2><label className="setup-check"><input type="checkbox" checked={gitEnabled} onChange={e => setGitEnabled(e.target.checked)} /> Mantener la proyección Git local</label><div className="setup-grid"><label className="field"><span>Autor técnico</span><input value={gitName} onChange={e => setGitName(e.target.value)} /></label><label className="field"><span>Correo técnico</span><input type="email" value={gitEmail} onChange={e => setGitEmail(e.target.value)} /></label></div></section>

    <section className="setup-section"><h2>{joining ? 'Incorporar este nodo' : 'Cuenta propietaria'}</h2><label className="field"><span>Código de incorporación</span><textarea rows={4} value={enrollment} onChange={e => setEnrollment(e.target.value)} placeholder="Vacío en el primer nodo; pégalo en los nodos adicionales" /></label>{!joining && <div className="setup-grid"><label className="field"><span>Usuario</span><input required value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" /></label><label className="field"><span>Nombre visible</span><input required value={displayName} onChange={e => setDisplayName(e.target.value)} /></label><label className="field"><span>Contraseña</span><input required type="password" minLength={passwordMin} value={password} onChange={e => setPassword(e.target.value)} autoComplete="new-password" /></label></div>}<p>Un nodo incorporado no crea otra cuenta: usuarios y permisos llegan desde el nodo activo.</p></section>

    {error && <div className="form-error">{error}</div>}
    <button className="button primary setup-submit" disabled={busy}>{busy ? 'Guardando…' : 'Guardar y arrancar RTFM'}</button>
  </form></main>
}
