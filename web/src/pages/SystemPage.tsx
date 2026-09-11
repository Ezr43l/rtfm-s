import { CheckCircle2, Clock3, Database, GitBranch, HardDrive, KeyRound, Network, RefreshCw, Save, Server, Settings, ShieldCheck, XCircle } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { ErrorState, LoadingState, PageHeader } from '../components/Feedback'
import { ContentCard } from '../layout/AppShell'
import { useAuth } from '../context/AuthContext'
import { api, formatDate, jsonBody } from '../lib/api'
import { hasFullControl } from '../lib/permissions'
import type { SystemConfiguration, SystemConfigurationValues, SystemStatus } from '../types'

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

export function ClusterPage() {
  const { session } = useAuth()
  const canSync = hasFullControl(session?.role)
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [error, setError] = useState('')
  const [syncing, setSyncing] = useState(false)
  const load = useCallback(() => { setError(''); api<SystemStatus>('/status').then(setStatus).catch(caught => setError(caught.message)) }, [])
  useEffect(load, [load])
  const sync = async () => {
    setSyncing(true); setError('')
    try { await api('/sync', { method: 'POST' }); load() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'No se pudo iniciar la sincronización') }
    finally { setSyncing(false) }
  }
  if (error && !status) return <ErrorState message={error} retry={load} />
  if (!status) return <LoadingState />
  return <><PageHeader eyebrow="ADMINISTRACIÓN" title="Nodos y alta disponibilidad" description="Estado operativo del nodo local, replicación documental y proyección Git." actions={canSync && <button className="button primary" onClick={() => void sync()} disabled={syncing}><RefreshCw size={17} className={syncing ? 'spin' : ''} /> {syncing ? 'Sincronizando…' : 'Sincronizar ahora'}</button>} />{error && <ErrorState message={error} />}
    <div className="status-grid">
      <ContentCard className="status-card"><div className="status-card-icon active"><Server size={23} /></div><span>Rol del nodo</span><strong>{status.role === 'active' ? 'Activo' : status.role}</strong><small>{status.node}</small></ContentCard>
      <ContentCard className="status-card"><div className="status-card-icon"><Clock3 size={23} /></div><span>Intervalo</span><strong>{Math.round(status.sync_interval_seconds / 60)} minutos</strong><small>Sincronización automática</small></ContentCard>
      <ContentCard className="status-card"><div className="status-card-icon"><Database size={23} /></div><span>Reloj lógico</span><strong>{status.sync.clock}</strong><small>{status.sync.documents} entidades documentales</small></ContentCard>
      <ContentCard className="status-card"><div className="status-card-icon"><HardDrive size={23} /></div><span>Retención</span><strong>{status.retention_days} días</strong><small>Contenido del vault</small></ContentCard>
    </div>
    <div className="system-grid">
      <ContentCard><div className="card-heading"><div><span className="eyebrow">RÉPLICAS</span><h2>Estado de sincronización</h2></div><Network size={21} /></div><div className="peer-list">{status.peers_configured.length ? status.peers_configured.map(peer => { const value = status.sync.peers[peer]; return <div className="peer-row" key={peer}><span className={`peer-icon ${value?.ok ? 'ok' : 'unknown'}`}>{value?.ok ? <CheckCircle2 size={18} /> : <XCircle size={18} />}</span><div><strong>{peer}</strong><span>{value?.ok ? 'Última réplica correcta' : value?.error || 'Todavía no verificado'}</span></div><time>{formatDate(value?.at)}</time></div> }) : <p className="muted">No hay pares configurados.</p>}</div></ContentCard>
      <ContentCard><div className="card-heading"><div><span className="eyebrow">HISTORIAL</span><h2>Repositorio Git</h2></div><GitBranch size={21} /></div><div className="git-status"><span className={`large-status ${status.git.ready ? 'ok' : 'bad'}`}>{status.git.ready ? <ShieldCheck size={25} /> : <XCircle size={25} />}</span><div><strong>{status.git.ready ? 'Repositorio preparado' : 'Repositorio no disponible'}</strong><span>{status.git.clean ? 'Sin cambios pendientes' : status.git.error || 'Hay cambios por registrar'}</span></div></div>{status.git.head && <div className="commit-value"><span>Último commit</span><code>{status.git.head.slice(0, 12)}</code></div>}</ContentCard>
    </div>
  </>
}

export function SystemSettingsPage() {
  const [configuration, setConfiguration] = useState<SystemConfiguration | null>(null)
  const [peersText, setPeersText] = useState('')
  const [portsText, setPortsText] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    setError('')
    api<SystemConfiguration>('/configuration').then(result => {
      setConfiguration(result)
      setPeersText(result.values.replication.peers.map(peer => `${peer.name} | ${peer.url}`).join('\n'))
      setPortsText(result.values.keepalived.service_ports.join(','))
    }).catch(caught => setError(caught.message))
  }, [])
  useEffect(load, [load])

  function patchSection<K extends 'public' | 'keepalived' | 'replication' | 'policy' | 'git'>(
    section: K,
    patch: Partial<SystemConfigurationValues[K]>,
  ) {
    setConfiguration(current => current ? {
      ...current,
      values: { ...current.values, [section]: { ...current.values[section], ...patch } },
    } : current)
  }

  const save = async () => {
    if (!configuration) return
    setSaving(true); setError(''); setNotice('')
    try {
      const values = {
        ...configuration.values,
        keepalived: {
          ...configuration.values.keepalived,
          service_ports: portsFromText(portsText),
        },
        replication: {
          ...configuration.values.replication,
          peers: peersFromText(peersText),
        },
      }
      await api<{ ok: boolean; restarting: boolean }>('/configuration', {
        method: 'PUT', ...jsonBody(values),
      })
      setNotice('Configuración guardada. RTFM se está reiniciando para aplicarla.')
      window.setTimeout(() => window.location.reload(), 1800)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'No se pudo guardar la configuración')
      setSaving(false)
    }
  }

  if (error && !configuration) return <ErrorState message={error} retry={load} />
  if (!configuration) return <LoadingState />
  const values = configuration.values
  const tokenConfigured = configuration.secrets.keepalived_api_key_configured

  return <><PageHeader eyebrow="AJUSTES" title="Configuración del sistema" description="Configuración funcional guardada dentro del volumen persistente de RTFM." />
    <div className="configuration-note"><Settings size={19} /><div><strong>La plantilla de Unraid sólo conserva la conexión con Docker.</strong><span>El puerto y el volumen se definen allí porque son necesarios antes de que la WebUI pueda arrancar; el resto se administra aquí.</span></div></div>
    {notice && <div className="security-banner success"><CheckCircle2 size={20} /><div><strong>Cambios guardados</strong><p>{notice}</p></div></div>}
    {error && <div className="security-banner error"><XCircle size={20} /><div><strong>No se pudo guardar</strong><p>{error}</p></div></div>}

    <ContentCard className="settings-list configuration-card"><div className="settings-section"><div className="settings-icon"><Server size={21} /></div><div><h2>Instancia y acceso</h2><p>Identidad del nodo, publicación y confianza en proxies.</p></div></div><div className="configuration-form-grid">
      <label className="field"><span>Nombre del nodo</span><input required value={values.node} onChange={event => setConfiguration({ ...configuration, values: { ...values, node: event.target.value } })} /></label>
      <label className="field"><span>Modo</span><select value={values.role_mode} onChange={event => setConfiguration({ ...configuration, values: { ...values, role_mode: event.target.value as SystemConfigurationValues['role_mode'] } })}><option value="active">Activo fijo · un solo nodo</option><option value="auto">Automático · IP flotante</option><option value="passive">Pasivo fijo · diagnóstico</option><option value="unknown">Bloqueado</option></select></label>
      <label className="field"><span>Esquema público</span><select value={values.public.scheme} onChange={event => patchSection('public', { scheme: event.target.value as 'http' | 'https' })}><option value="http">HTTP</option><option value="https">HTTPS</option></select></label>
      <label className="field"><span>Proxies de confianza</span><input value={values.public.forwarded_allow_ips} onChange={event => patchSection('public', { forwarded_allow_ips: event.target.value })} /></label>
      <label className="field"><span>IP flotante manual</span><input value={values.public.floating_ip} onChange={event => patchSection('public', { floating_ip: event.target.value })} placeholder="Opcional" /></label>
      <label className="field"><span>URL pública flotante</span><input value={values.public.floating_url} onChange={event => patchSection('public', { floating_url: event.target.value })} placeholder="Opcional" /></label>
    </div><label className="setup-check configuration-check"><input type="checkbox" checked={values.public.session_cookie_secure} onChange={event => patchSection('public', { session_cookie_secure: event.target.checked })} /><span><strong>Cookie de sesión Secure</strong><small>Actívala sólo si todo el acceso a RTFM utiliza HTTPS.</small></span></label></ContentCard>

    <ContentCard className="settings-list configuration-card"><div className="settings-section"><div className="settings-icon"><KeyRound size={21} /></div><div><h2>Conexión con Keepalived</h2><p>Opcional. Permite que RTFM reserve y utilice una dirección flotante.</p></div></div>
      <ol className="configuration-steps">
        <li>En Keepalived abre <strong>Cuenta → Claves API</strong> y crea una clave llamada, por ejemplo, <strong>RTFM</strong>, con el permiso <code>claims:write</code>.</li>
        <li>Usa la dirección del <strong>primer nodo de Keepalived</strong>, que es su coordinador o escritor. No uses aquí la IP flotante que RTFM va a solicitar.</li>
        <li>Pega la clave una sola vez. RTFM genera por sí mismo el identificador de reclamación y conoce su puerto y su ruta de salud.</li>
      </ol>
      <div className="configuration-form-grid aligned-fields">
        <label className="field"><span>Dirección del Keepalived coordinador</span><input value={values.keepalived.url} onChange={event => patchSection('keepalived', { url: event.target.value })} placeholder="Ej. http://192.0.2.10:6060" /><small>URL base del panel, con protocolo y puerto, pero sin añadir <code>/api/claims</code>.</small></label>
        <label className="field"><span>Clave API para RTFM</span><input type="password" value={values.keepalived.api_key} onChange={event => patchSection('keepalived', { api_key: event.target.value })} placeholder={tokenConfigured ? 'Configurada · déjala vacía para conservarla' : 'Ej. fip_…'} autoComplete="new-password" /><small>Empieza por <code>fip_</code>. Para desconectar Keepalived, vacía también el campo de dirección.</small></label>
      </div>
      <label className="setup-check configuration-check"><input type="checkbox" checked={values.keepalived.allow_insecure_http} onChange={event => patchSection('keepalived', { allow_insecure_http: event.target.checked })} /><span><strong>Permitir HTTP dentro de la red privada</strong><small>Actívalo sólo cuando la dirección anterior comience por <code>http://</code> y el tráfico permanezca dentro de una LAN o VPN de confianza.</small></span></label>
      <details className="configuration-advanced"><summary><span>Ajustes avanzados de la reclamación</span><small>Los valores predeterminados son correctos para una instalación normal de RTFM.</small></summary><div className="configuration-form-grid aligned-fields">
        <label className="field"><span>Nombre técnico del servicio</span><input value={values.keepalived.service} onChange={event => patchSection('keepalived', { service: event.target.value })} placeholder="rtfm" /><small>Debe ser el mismo en todos los nodos de RTFM.</small></label>
        <label className="field"><span>Descripción visible en Keepalived</span><input value={values.keepalived.description} onChange={event => patchSection('keepalived', { description: event.target.value })} placeholder="RTFM" /><small>Texto que identificará la aplicación en el panel.</small></label>
        <label className="field"><span>Identificador estable de reclamación</span><input value={values.keepalived.claim_id} onChange={event => patchSection('keepalived', { claim_id: event.target.value })} placeholder="RTFM lo genera automáticamente" /><small>No lo cambies después de reservar la IP: evita crear otra reclamación accidentalmente.</small></label>
        <label className="field"><span>Ruta de salud de RTFM</span><input value={values.keepalived.health_path} onChange={event => patchSection('keepalived', { health_path: event.target.value })} placeholder="/api/health" /><small>Keepalived la consulta localmente para decidir si este nodo puede sostener la IP.</small></label>
        <label className="field"><span>Puertos públicos adicionales</span><input value={portsText} onChange={event => setPortsText(event.target.value)} placeholder="Ej. 443,8443" /><small>Opcional. El puerto propio de RTFM ya se incluye automáticamente.</small></label>
        <label className="field"><span>Espera máxima de la API</span><input type="number" min="1" max="30" value={values.keepalived.timeout_seconds} onChange={event => patchSection('keepalived', { timeout_seconds: Number(event.target.value) })} /><small>Segundos que RTFM espera una respuesta de Keepalived.</small></label>
      </div><label className="field"><span>CA privada de Keepalived en formato PEM</span><textarea rows={4} value={values.keepalived.ca_pem} onChange={event => patchSection('keepalived', { ca_pem: event.target.value })} placeholder="Sólo para HTTPS con una autoridad certificadora privada" /><small>No es necesaria con HTTP ni con certificados HTTPS reconocidos públicamente.</small></label></details>
    </ContentCard>

    <ContentCard className="settings-list configuration-card"><div className="settings-section"><div className="settings-icon"><Network size={21} /></div><div><h2>Réplica entre nodos RTFM</h2><p>Opcional. Mantiene la documentación y las cuentas en las demás instancias.</p></div></div>
      <div className="configuration-guidance"><strong>Indica únicamente los otros nodos.</strong><span>Escribe uno por línea como <code>nombre | URL directa</code>. Usa la dirección propia de cada servidor, no la IP flotante. En una instalación de un solo nodo, déjalo vacío.</span></div>
      <label className="field"><span>Otros nodos RTFM</span><textarea rows={4} value={peersText} onChange={event => setPeersText(event.target.value)} placeholder={'Ej. node-b | http://192.0.2.21:7400\nEj. node-c | http://192.0.2.22:7400'} /><small>El nombre debe coincidir con el configurado en ese nodo. Las credenciales de réplica se comparten mediante el código de incorporación.</small></label>
      <label className="field configuration-short-field"><span>Tamaño máximo de una réplica</span><input type="number" min="1" max="4096" value={values.replication.max_mb} onChange={event => patchSection('replication', { max_mb: Number(event.target.value) })} /><small>Límite en MB para rechazar paquetes inesperadamente grandes; normalmente no es necesario modificarlo.</small></label>
      <label className="setup-check configuration-check"><input type="checkbox" checked={values.replication.allow_insecure_http} onChange={event => patchSection('replication', { allow_insecure_http: event.target.checked })} /><span><strong>Permitir réplica HTTP dentro de la red privada</strong><small>Actívalo sólo si las URL anteriores usan <code>http://</code> dentro de una LAN o VPN de confianza.</small></span></label>
      <details className="configuration-advanced"><summary><span>Certificado avanzado para la réplica</span><small>Sólo es necesario con HTTPS y una autoridad certificadora privada.</small></summary><label className="field"><span>CA privada de réplica en formato PEM</span><textarea rows={4} value={values.replication.ca_pem} onChange={event => patchSection('replication', { ca_pem: event.target.value })} placeholder="-----BEGIN CERTIFICATE-----" /></label></details>
    </ContentCard>

    <ContentCard className="settings-list configuration-card"><div className="settings-section"><div className="settings-icon"><ShieldCheck size={21} /></div><div><h2>Políticas</h2><p>Conservación, sincronización, sesiones y acceso.</p></div></div><div className="configuration-form-grid policy-grid">
      <label className="field"><span>Retención del vault (días)</span><input type="number" min="1" max="36500" value={values.policy.retention_days} onChange={event => patchSection('policy', { retention_days: Number(event.target.value) })} /></label>
      <label className="field"><span>Sincronización (segundos)</span><input type="number" min="30" max="86400" value={values.policy.sync_interval_seconds} onChange={event => patchSection('policy', { sync_interval_seconds: Number(event.target.value) })} /></label>
      <label className="field"><span>Imagen máxima (MB)</span><input type="number" min="1" max="100" value={values.policy.max_image_size_mb} onChange={event => patchSection('policy', { max_image_size_mb: Number(event.target.value) })} /></label>
      <label className="field"><span>Sesión (horas)</span><input type="number" min="1" max="8760" value={values.policy.session_hours} onChange={event => patchSection('policy', { session_hours: Number(event.target.value) })} /></label>
      <label className="field"><span>Intentos de login</span><input type="number" min="3" max="50" value={values.policy.login_max_attempts} onChange={event => patchSection('policy', { login_max_attempts: Number(event.target.value) })} /></label>
      <label className="field"><span>Ventana de login (s)</span><input type="number" min="30" max="3600" value={values.policy.login_window_seconds} onChange={event => patchSection('policy', { login_window_seconds: Number(event.target.value) })} /></label>
      <label className="field"><span>Contraseña mínima</span><input type="number" min="12" max="256" value={values.policy.password_min_length} onChange={event => patchSection('policy', { password_min_length: Number(event.target.value) })} /></label>
      <label className="field"><span>Nombre para 2FA</span><input value={values.policy.totp_issuer} onChange={event => patchSection('policy', { totp_issuer: event.target.value })} /></label>
    </div></ContentCard>

    <ContentCard className="settings-list configuration-card"><div className="settings-section"><div className="settings-icon"><GitBranch size={21} /></div><div><h2>Historial Git</h2><p>Proyección local versionada de los documentos.</p></div></div><label className="setup-check configuration-check"><input type="checkbox" checked={values.git.enabled} onChange={event => patchSection('git', { enabled: event.target.checked })} /><span><strong>Mantener la proyección Git local</strong><small>El repositorio permanece dentro del volumen persistente.</small></span></label><div className="configuration-form-grid"><label className="field"><span>Autor técnico</span><input value={values.git.author_name} onChange={event => patchSection('git', { author_name: event.target.value })} /></label><label className="field"><span>Correo técnico</span><input type="email" value={values.git.author_email} onChange={event => patchSection('git', { author_email: event.target.value })} /></label></div></ContentCard>

    <div className="configuration-actions"><span>Al guardar, RTFM valida todos los valores y reinicia este único contenedor.</span><button className="button primary" disabled={saving} onClick={() => void save()}><Save size={17} />{saving ? 'Guardando…' : 'Guardar configuración'}</button></div>
  </>
}
