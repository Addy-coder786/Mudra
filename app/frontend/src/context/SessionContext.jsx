import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { API_BASE_URL } from '../services/signRecognizer'
import { chooseSession, clearDemoSession, demoSession, loadDemoSession, saveDemoSession } from '../services/session'

/**
 * Who is signed in (services/session.js). On load the server is asked for a Google session (/auth/me); when there is
 * none, or the server cannot be reached, the local session kept in this browser is used. `ready` turns true after
 * that first answer, so the route guards do not send a Google user to /welcome before the cookie has been read.
 * `googleConfigured` tells the sign-in page whether this server can do Google sign-in at all.
 */
const SessionContext = createContext(null)

export function SessionProvider({ children }) {
  const [session, setSession] = useState(loadDemoSession)
  const [ready, setReady] = useState(false)
  const [googleConfigured, setGoogleConfigured] = useState(null)

  const refresh = useCallback(async () => {
    let me = null
    try {
      const r = await fetch(`${API_BASE_URL}/auth/me`, { credentials: 'include', signal: AbortSignal.timeout(4000) })
      if (r.ok) me = await r.json()
    } catch { /* offline or an older server: the local session decides */ }
    if (me) setGoogleConfigured(Boolean(me.google_configured))
    setSession(chooseSession(me))
    setReady(true)
    return me
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const signIn = useCallback((role, name) => {
    const s = demoSession(role, name)
    saveDemoSession(s)
    setSession(s)
  }, [])

  const signOut = useCallback(() => {
    const wasGoogle = session?.google
    clearDemoSession()
    setSession(null)
    if (wasGoogle) fetch(`${API_BASE_URL}/auth/logout`, { method: 'POST', credentials: 'include' }).catch(() => {})
  }, [session])

  return (
    <SessionContext.Provider value={{ session, ready, googleConfigured, signIn, signOut, refresh }}>
      {children}
    </SessionContext.Provider>
  )
}

export function useSession() {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error('useSession must be used within SessionProvider')
  return ctx
}
