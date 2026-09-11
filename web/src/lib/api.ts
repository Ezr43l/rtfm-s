const API_ROOT = '/api/v1'

export class ApiError extends Error {
  status: number
  code: string
  requestId?: string

  constructor(status: number, message: string, code = 'UNKNOWN', requestId?: string) {
    super(message)
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

let csrfToken = sessionStorage.getItem('rtfm-csrf') || ''

export function setCsrfToken(value: string) {
  csrfToken = value
  if (value) sessionStorage.setItem('rtfm-csrf', value)
  else sessionStorage.removeItem('rtfm-csrf')
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || 'GET').toUpperCase()
  const headers = new Headers(options.headers)
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) headers.set('X-CSRF-Token', csrfToken)
  const response = await fetch(`${API_ROOT}${path}`, { ...options, headers, credentials: 'same-origin' })
  if (response.status === 204) return undefined as T
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = body.error || {}
    throw new ApiError(response.status, error.message || `Error HTTP ${response.status}`, error.code, error.request_id)
  }
  return body as T
}

export function jsonBody(value: unknown): Pick<RequestInit, 'body' | 'headers'> {
  return { body: JSON.stringify(value), headers: { 'Content-Type': 'application/json' } }
}

export function formatDate(value?: string | null, includeTime = true): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('es-ES', includeTime
    ? { dateStyle: 'medium', timeStyle: 'short' }
    : { dateStyle: 'medium' }).format(date)
}

export function relativeDate(value?: string | null): string {
  if (!value) return 'Sin datos'
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000)
  const formatter = new Intl.RelativeTimeFormat('es', { numeric: 'auto' })
  const ranges: [number, Intl.RelativeTimeFormatUnit][] = [[31536000, 'year'], [2592000, 'month'], [86400, 'day'], [3600, 'hour'], [60, 'minute']]
  for (const [amount, unit] of ranges) if (Math.abs(seconds) >= amount) return formatter.format(Math.round(seconds / amount), unit)
  return formatter.format(seconds, 'second')
}
