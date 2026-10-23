/**
 * Cloud copies of a recording (the team's Supabase, through the backend's /cloud/recordings): the camera video from
 * MediaRecorder and the track points (hand + body landmarks per frame, in the studio's {t, pose, lh, rh, face}
 * frame format). The server keeps the Supabase key; the browser only posts here. See docs/CLOUD_STORAGE.md.
 */
import { API_BASE_URL } from './signRecognizer'

export const CLOUD_SAVE_KEY = 'signline_cloud_save'
export const PURPOSES = ['learning', 'communication', 'custom_gesture']
const MAX_FRAMES = 9000 // ~5 minutes at 30 fps: a long Communication session keeps its first frames

let statusCache = null

/** {configured, bucket} from the server (cached; null when the server cannot be reached). */
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

export function pickMimeType(isSupported = (m) => (typeof MediaRecorder !== 'undefined' ? MediaRecorder.isTypeSupported(m) : false)) {
  return ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm', 'video/mp4'].find(isSupported) || ''
}

/** Records the camera stream and the track points of one session; `stop()` gives both. */
export class CloudRecorder {
  constructor() {
    this.recorder = null
    this.chunks = []
    this.frames = []
    this.startedAt = 0
    this.dropped = 0
    this.width = 0
    this.height = 0
  }

  get active() { return this.startedAt > 0 }

  start(stream) {
    this.stop()
    this.chunks = []
    this.frames = []
    this.dropped = 0
    this.startedAt = performance.now()
    if (stream && typeof MediaRecorder !== 'undefined') {
      try {
        const mimeType = pickMimeType()
        const videoOnly = typeof MediaStream !== 'undefined' ? new MediaStream(stream.getVideoTracks()) : stream
        this.recorder = new MediaRecorder(videoOnly, mimeType ? { mimeType, videoBitsPerSecond: 1_500_000 } : undefined)
        this.recorder.ondataavailable = (e) => { if (e.data && e.data.size) this.chunks.push(e.data) }
        this.recorder.start(1000)
      } catch (err) {
        console.warn('Video recording is not available; only the track points will be saved:', err)
        this.recorder = null
      }
    }
  }

  addFrame(results) {
    if (!this.active) return
    if (results.width) { this.width = results.width; this.height = results.height }
    if (this.frames.length >= MAX_FRAMES) { this.dropped += 1; return }
    this.frames.push(toSkeletonFrame(results, performance.now() - this.startedAt))
  }

  /** Resolves to {video: Blob|null, skeleton, duration, fps, width, height} and resets. */
  async stop() {
    if (!this.active) return null
    const duration = (performance.now() - this.startedAt) / 1000
    const recorder = this.recorder
    this.recorder = null
    let video = null
    if (recorder) {
      const mimeType = recorder.mimeType || 'video/webm'
      await new Promise((resolve) => {
        if (recorder.state === 'inactive') { resolve(); return }
        recorder.onstop = resolve
        try { recorder.stop() } catch { resolve() }
      })
      if (this.chunks.length) video = new Blob(this.chunks, { type: mimeType })
    }
    const frames = this.frames
    const fps = duration > 0 && frames.length > 1 ? Math.round((frames.length - 1) / duration * 10) / 10 : 0
    const out = { video, skeleton: { fps, frames }, duration: Math.round(duration * 100) / 100, fps, width: this.width, height: this.height }
    this.startedAt = 0
    this.chunks = []
    this.frames = []
    return out
  }
}

/** Posts a stopped recording to the backend; resolves to the server's answer. */
export async function uploadRecording({ purpose, label, video, skeleton, duration = 0, fps = 0, notes = '', width = 0, height = 0 }, fetchImpl = fetch) {
  if (!PURPOSES.includes(purpose)) throw new Error(`unknown purpose ${purpose}`)
  const form = new FormData()
  form.append('purpose', purpose)
  form.append('label', label || 'Sign Gesture')
  form.append('duration', String(duration))
  form.append('fps', String(fps))
  form.append('notes', notes)
  form.append('width', String(width))
  form.append('height', String(height))
  if (skeleton && skeleton.frames?.length) form.append('skeleton', JSON.stringify(skeleton))
  if (video) form.append('video', video, `recording_${Date.now()}.${video.type.includes('mp4') ? 'mp4' : 'webm'}`)
  const r = await fetchImpl(`${API_BASE_URL}/cloud/recordings`, { method: 'POST', body: form, credentials: 'include' })
  const body = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(body.detail || `Cloud save failed (${r.status})`)
  return body
}
