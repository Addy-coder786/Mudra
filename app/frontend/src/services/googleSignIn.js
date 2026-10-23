/**
 * Google sign-in from the browser side (the server side is mudra_api/google_auth.py).
 *
 * The page opens `${apiBase}/auth/google/start` in a popup. When Google is done, the popup's last page posts
 * { type: RESULT_TYPE, status } to the opener (postMessage) and on a BroadcastChannel, then closes; the page also
 * polls /auth/me, so a popup that was turned into a full tab (popup blockers) still ends the wait. Result statuses:
 * success (with the user), not_configured (no Google client on this server), cancelled, failed.
 *
 * `win` and `fetchImpl` are injectable for tests.
 */
export const RESULT_TYPE = 'signline-google-auth'
export const POPUP_FEATURES = 'width=520,height=660,resizable=yes,scrollbars=yes,popup=yes'

export function googleStartUrl(apiBase, next = '/app/home') {
  return `${apiBase}/auth/google/start?next=${encodeURIComponent(next)}`
}

/** Starts the popup flow; `onResult` is called exactly once. Returns a function that abandons the wait. */
export function startGoogleSignIn({ apiBase, next = '/app/home', onResult, win = window, fetchImpl = fetch,
                                    pollMs = 1000, timeoutMs = 10 * 60 * 1000 }) {
  const url = googleStartUrl(apiBase, next)
  let done = false
  let closedAt = null
  let channel = null
  const timers = []
  const cleanup = () => {
    timers.forEach((t) => { win.clearInterval(t); win.clearTimeout(t) })
    win.removeEventListener('message', onMessage)
    try { channel?.close() } catch { /* already closed */ }
  }
  const finish = (result) => {
    if (done) return
    done = true
    cleanup()
    onResult(result)
  }
  const checkMe = async () => {
    try {
      const r = await fetchImpl(`${apiBase}/auth/me`, { credentials: 'include' })
      if (!r.ok) return false
      const data = await r.json()
      if (data?.user) { finish({ status: 'success', user: data.user }); return true }
    } catch { /* the server is not reachable right now: keep waiting */ }
    return false
  }
  const handle = (data) => {
    if (!data || data.type !== RESULT_TYPE) return
    if (data.status === 'success') checkMe().then((ok) => { if (!ok) finish({ status: 'failed' }) })
    else finish({ status: data.status })
  }
  const onMessage = (event) => { if (event.origin === win.location.origin) handle(event.data) }
  win.addEventListener('message', onMessage)
  if (typeof win.BroadcastChannel === 'function') {
    channel = new win.BroadcastChannel(RESULT_TYPE)
    channel.onmessage = (event) => handle(event.data)
  }
  const popup = win.open(url, RESULT_TYPE, POPUP_FEATURES)
  if (!popup) { // popup blocked: Google in this tab; the callback page continues to `next`
    done = true
    cleanup()
    win.location.assign(url)
    return () => {}
  }
  timers.push(win.setInterval(() => { checkMe() }, pollMs))
  timers.push(win.setInterval(() => {
    // the popup was closed without a result: one last look at the session, then "cancelled"
    if (!popup.closed) return
    closedAt ??= Date.now()
    if (Date.now() - closedAt > 1200) checkMe().then((ok) => { if (!ok) finish({ status: 'cancelled' }) })
  }, 400))
  timers.push(win.setTimeout(() => finish({ status: 'failed' }), timeoutMs))
  return () => { done = true; cleanup() }
}
