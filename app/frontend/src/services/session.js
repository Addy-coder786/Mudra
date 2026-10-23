/**
 * The signed-in person, in one of two forms:
 * - a Google session (google: true) read from the server's cookie through /auth/me: email, name, picture, role;
 * - a local session (google: false, demo: true) kept in this browser's localStorage, as before Google sign-in
 *   existed: the automatic fallback when Google is not configured, cancelled or fails. Anyone can choose the
 *   learner role this way; the admin workspace needs Google.
 */
export const DEMO_KEY = 'signline_demo_session'

export function loadDemoSession(storage = globalThis.localStorage) {
  try {
    const s = JSON.parse(storage?.getItem(DEMO_KEY) || 'null')
    return s && (s.role === 'user' || s.role === 'admin') ? { ...s, demo: true, google: false } : null
  } catch {
    return null
  }
}

export function demoSession(role, name) {
  return { role, name: (name || '').trim() || (role === 'admin' ? 'Admin' : 'Friend'), demo: true, google: false }
}

export function saveDemoSession(session, storage = globalThis.localStorage) {
  try { storage?.setItem(DEMO_KEY, JSON.stringify(session)) } catch { /* not remembered after reload */ }
}

export function clearDemoSession(storage = globalThis.localStorage) {
  try { storage?.removeItem(DEMO_KEY) } catch { /* nothing stored */ }
}

/** A Google user from /auth/me as the app's session; null for anything that is not a signed-in user. */
export function sessionFromGoogle(user) {
  if (!user || (user.role !== 'user' && user.role !== 'admin')) return null
  const picture = typeof user.picture === 'string' && user.picture.startsWith('https://') ? user.picture : null
  return { role: user.role, name: user.name || user.email || 'Friend', email: user.email || null, picture, google: true, demo: false }
}

/** Which session the app uses: the Google one when the server has it, else the local one. */
export function chooseSession(meResponse, storage = globalThis.localStorage) {
  return sessionFromGoogle(meResponse?.user) || loadDemoSession(storage)
}
