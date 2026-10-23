import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RESULT_TYPE, googleStartUrl, startGoogleSignIn } from '../googleSignIn'

const ORIGIN = 'http://localhost:3000'

function fakeWindow({ popup = { closed: false } } = {}) {
  const listeners = {}
  return {
    popup,
    listeners,
    location: { origin: ORIGIN, assign: vi.fn() },
    open: vi.fn(() => popup),
    addEventListener: vi.fn((type, fn) => { listeners[type] = fn }),
    removeEventListener: vi.fn((type) => { delete listeners[type] }),
    setInterval: (fn, ms) => setInterval(fn, ms),
    clearInterval: (id) => clearInterval(id),
    setTimeout: (fn, ms) => setTimeout(fn, ms),
    clearTimeout: (id) => clearTimeout(id),
  }
}

const meResponse = (user) => ({ ok: true, json: async () => ({ user, google_configured: true }) })

describe('Google sign-in popup flow', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('builds the start URL with the next path', () => {
    expect(googleStartUrl('http://api', '/app/learning')).toBe('http://api/auth/google/start?next=%2Fapp%2Flearning')
  })

  it('reports success with the user once the popup says so and /auth/me confirms it', async () => {
    const win = fakeWindow()
    const fetchImpl = vi.fn(async () => meResponse({ email: 'a@b.c', name: 'A', role: 'user' }))
    const onResult = vi.fn()
    startGoogleSignIn({ apiBase: 'http://api', onResult, win, fetchImpl })
    expect(win.open).toHaveBeenCalledWith(expect.stringContaining('/auth/google/start'), RESULT_TYPE, expect.any(String))
    win.listeners.message({ origin: ORIGIN, data: { type: RESULT_TYPE, status: 'success' } })
    await vi.runOnlyPendingTimersAsync()
    expect(onResult).toHaveBeenCalledTimes(1)
    expect(onResult.mock.calls[0][0]).toEqual({ status: 'success', user: { email: 'a@b.c', name: 'A', role: 'user' } })
    expect(fetchImpl).toHaveBeenCalledWith('http://api/auth/me', { credentials: 'include' })
  })

  it('ignores messages from other origins and passes on cancelled / not_configured without fetching', () => {
    const win = fakeWindow()
    const fetchImpl = vi.fn()
    const onResult = vi.fn()
    startGoogleSignIn({ apiBase: 'http://api', onResult, win, fetchImpl })
    win.listeners.message({ origin: 'https://evil.example', data: { type: RESULT_TYPE, status: 'success' } })
    expect(onResult).not.toHaveBeenCalled()
    win.listeners.message({ origin: ORIGIN, data: { type: RESULT_TYPE, status: 'not_configured' } })
    expect(onResult).toHaveBeenCalledWith({ status: 'not_configured' })
    expect(fetchImpl).not.toHaveBeenCalled()
    expect(win.removeEventListener).toHaveBeenCalled() // listeners are gone after the result
  })

  it('falls back to a full-page redirect when the popup is blocked', () => {
    const win = fakeWindow({ popup: null })
    const onResult = vi.fn()
    startGoogleSignIn({ apiBase: 'http://api', onResult, win, fetchImpl: vi.fn() })
    expect(win.location.assign).toHaveBeenCalledWith(expect.stringContaining('/auth/google/start'))
    expect(onResult).not.toHaveBeenCalled()
  })

  it('treats a popup closed without a result as cancelled, after one last session check', async () => {
    const popup = { closed: false }
    const win = fakeWindow({ popup })
    const fetchImpl = vi.fn(async () => meResponse(null))
    const onResult = vi.fn()
    startGoogleSignIn({ apiBase: 'http://api', onResult, win, fetchImpl })
    popup.closed = true
    await vi.advanceTimersByTimeAsync(2500)
    expect(onResult).toHaveBeenCalledTimes(1)
    expect(onResult).toHaveBeenCalledWith({ status: 'cancelled' })
  })
})
