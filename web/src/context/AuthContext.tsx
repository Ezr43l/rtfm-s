import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, ApiError, jsonBody, setCsrfToken } from '../lib/api'
import type { Session } from '../types'

interface AuthValue {
  session: Session | null
  loading: boolean
  login: (actor: string, credential: string, otp?: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const current = await api<Session>('/auth/session')
      setSession(current)
      setCsrfToken(current.csrf_token)
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error
      setSession(null)
      setCsrfToken('')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  const login = useCallback(async (actor: string, credential: string, otp?: string) => {
    const current = await api<Session>('/auth/session', { method: 'POST', ...jsonBody({ actor, credential, otp: otp || null }) })
    setSession(current)
    setCsrfToken(current.csrf_token)
  }, [])

  const logout = useCallback(async () => {
    await api('/auth/session', { method: 'DELETE' })
    setSession(null)
    setCsrfToken('')
  }, [])

  const value = useMemo(() => ({ session, loading, login, logout, refresh }), [session, loading, login, logout, refresh])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth debe usarse dentro de AuthProvider')
  return value
}
