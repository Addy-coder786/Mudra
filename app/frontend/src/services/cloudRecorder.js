/**
 * Cloud copies of a recording's **track points** (the team's Supabase, through the backend's /cloud/recordings):
 * the hand and body landmarks of every tracked frame, in the studio's {t, pose, lh, rh, face} frame format.
 * No video and no camera image is recorded or sent: nothing in this module touches the picture. The server keeps
 * the Supabase key; the browser only posts numbers here. See docs/CLOUD_STORAGE.md.
 */
import { API_BASE_URL } from './signRecognizer'

export const CLOUD_SAVE_KEY = 'signline_cloud_save'
export const PURPOSES = ['learning', 'communication', 'custom_gesture']
const MAX_FRAMES = 9000 // ~5 minutes at 30 fps: a long Communication session keeps its first frames

let statusCache = null

/** {configured, stores, stores_video: false} from the server (cached; null when the server cannot be reached). */
export async function getCloudStatus(force = false) {
  if (statusCache && !force) return statusCache
  try {
    const r = await fetch(`${API_BASE_URL}/cloud/status`)
    statusCache = r.ok ? await r.json() : null
  } catch {
    statusCache = null
  }
  return statusCache
}

/** The person's choice (default on): remembered in this browser. */
export function cloudSaveEnabled(storage = globalThis.localStorage) {
  try { return storage?.getItem(CLOUD_SAVE_KEY) !== 'off' } catch { return true }
}

export function setCloudSaveEnabled(on, storage = globalThis.localStorage) {
  try { storage?.setItem(CLOUD_SAVE_KEY, on ? 'on' : 'off') } catch { /* not remembered */ }
}

const r4 = (v) => Math.round(v * 10000) / 10000

/** One tracker result as the studio's skeleton frame; `t` in ms since the recording started. */
export function toSkeletonFrame(results, t) {
  const hands = results.multiHandLandmarks || []
  const sides = results.multiHandedness || []
  let lh = null
  let rh = null
  hands.forEach((points, i) => {
    const pts = points.map((p) => ({ x: r4(p.x), y: r4(p.y), z: r4(p.z || 0) }))
    // MediaPipe labels the hand as seen in a mirrored selfie picture: its "Right" is the signer's left
    const label = sides[i]?.label || ''
    if (label === 'Right' && !lh) lh = pts
    else if (label === 'Left' && !rh) rh = pts
    else if (!lh) lh = pts
    else if (!rh) rh = pts
  })
  const pose = results.poseLandmarks
    ? results.poseLandmarks.map((p) => ({ x: r4(p.x), y: r4(p.y), z: r4(p.z || 0), v: Math.round((p.visibility ?? 1) * 100) / 100 }))
    : null
  return { t: Math.round(t), pose, lh, rh, face: null }
}

/** Collects the track points of one session; `stop()` gives them. Never touches the camera stream. */
export class CloudRecorder {
  constructor() {
    this.frames = []
    this.startedAt = 0
    this.dropped = 0
    this.width = 0
    this.height = 0
  }

  get active() { return this.startedAt > 0 }

  start() {
    this.frames = []
    this.dropped = 0
    this.startedAt = performance.now()
  }

  addFrame(results) {
    if (!this.active) return
    if (results.width) { this.width = results.width; this.height = results.height }
    if (this.frames.length >= MAX_FRAMES) { this.dropped += 1; return }
    this.frames.push(toSkeletonFrame(results, performance.now() - this.startedAt))
  }

  /** {skeleton, duration, fps, width, height} and resets; null when nothing was started. */
  stop() {
    if (!this.active) return null
    const duration = (performance.now() - this.startedAt) / 1000
    const frames = this.frames
    const fps = duration > 0 && frames.length > 1 ? Math.round((frames.length - 1) / duration * 10) / 10 : 0
    const out = { skeleton: { fps, frames }, duration: Math.round(duration * 100) / 100, fps, width: this.width, height: this.height }
    this.startedAt = 0
    this.frames = []
    return out
  }
}

/** Posts a stopped recording's track points to the backend; resolves to the server's answer. */
export async function uploadRecording({ purpose, label, skeleton, duration = 0, fps = 0, notes = '', width = 0, height = 0 }, fetchImpl = fetch) {
  if (!PURPOSES.includes(purpose)) throw new Error(`unknown purpose ${purpose}`)
  if (!skeleton?.frames?.length) throw new Error('no track points to save')
  const form = new FormData()
  form.append('purpose', purpose)
  form.append('label', label || 'Sign Gesture')
  form.append('skeleton', JSON.stringify(skeleton))
  form.append('duration', String(duration))
  form.append('fps', String(fps))
  form.append('notes', notes)
  form.append('width', String(width))
  form.append('height', String(height))
  const r = await fetchImpl(`${API_BASE_URL}/cloud/recordings`, { method: 'POST', body: form, credentials: 'include' })
  const body = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(body.detail || `Cloud save failed (${r.status})`)
  return body
}
