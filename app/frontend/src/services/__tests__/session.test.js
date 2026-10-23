import { describe, expect, it } from 'vitest'
import { DEMO_KEY, chooseSession, clearDemoSession, demoSession, loadDemoSession, saveDemoSession, sessionFromGoogle } from '../session'

const storage = () => {
  const m = new Map()
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, v), removeItem: (k) => m.delete(k) }
}

describe('sessions', () => {
  it('keeps the local session in the browser as before, and only valid roles', () => {
    const s = storage()
    expect(loadDemoSession(s)).toBeNull()
    saveDemoSession(demoSession('user', '  Priya '), s)
    expect(JSON.parse(s.getItem(DEMO_KEY)).name).toBe('Priya')
    expect(loadDemoSession(s)).toMatchObject({ role: 'user', name: 'Priya', demo: true, google: false })
    expect(demoSession('user', '').name).toBe('Friend')
    s.setItem(DEMO_KEY, JSON.stringify({ role: 'root', name: 'x' }))
    expect(loadDemoSession(s)).toBeNull()
    clearDemoSession(s)
    expect(s.getItem(DEMO_KEY)).toBeNull()
  })

  it('turns a Google user into a session with a safe picture URL', () => {
    expect(sessionFromGoogle({ email: 'a@b.c', name: 'Asha', picture: 'https://lh3.googleusercontent.com/p', role: 'admin' }))
      .toEqual({ role: 'admin', name: 'Asha', email: 'a@b.c', picture: 'https://lh3.googleusercontent.com/p', google: true, demo: false })
    expect(sessionFromGoogle({ email: 'a@b.c', picture: 'http://insecure/p', role: 'user' })).toMatchObject({ name: 'a@b.c', picture: null })
    expect(sessionFromGoogle({ email: 'a@b.c', role: 'owner' })).toBeNull()
    expect(sessionFromGoogle(null)).toBeNull()
  })

  it('prefers the Google session over the local one, and uses the local one without Google', () => {
    const s = storage()
    saveDemoSession(demoSession('user', 'Local'), s)
    expect(chooseSession({ user: { email: 'g@x.y', name: 'G', role: 'user' } }, s)).toMatchObject({ name: 'G', google: true })
    expect(chooseSession({ user: null }, s)).toMatchObject({ name: 'Local', google: false })
    expect(chooseSession(null, s)).toMatchObject({ name: 'Local' })
    clearDemoSession(s)
    expect(chooseSession(null, s)).toBeNull()
  })
})
