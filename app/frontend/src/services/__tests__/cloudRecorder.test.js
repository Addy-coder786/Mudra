import { describe, expect, it, vi } from 'vitest'
import { CLOUD_SAVE_KEY, cloudSaveEnabled, pickMimeType, setCloudSaveEnabled, toSkeletonFrame, uploadRecording } from '../cloudRecorder'

const hand = (x) => Array.from({ length: 21 }, (_, i) => ({ x: x + i * 0.001, y: 0.5, z: -0.01 }))

describe('cloud copies of recordings', () => {
  it('turns tracker results into the studio frame format, signer-left as lh', () => {
    const pose = Array.from({ length: 33 }, () => ({ x: 0.5, y: 0.4, z: 0, visibility: 0.987 }))
    const f = toSkeletonFrame({
      multiHandLandmarks: [hand(0.6), hand(0.3)],
      multiHandedness: [{ label: 'Left', score: 0.9 }, { label: 'Right', score: 0.9 }], // mirrored picture labels
      poseLandmarks: pose,
    }, 123.6)
    expect(f.t).toBe(124)
    expect(f.rh[0].x).toBeCloseTo(0.6) // MediaPipe "Left" in the mirror = the signer's right hand
    expect(f.lh[0].x).toBeCloseTo(0.3)
    expect(f.pose).toHaveLength(33)
    expect(f.pose[0]).toEqual({ x: 0.5, y: 0.4, z: 0, v: 0.99 })
    expect(f.face).toBeNull()
    expect(toSkeletonFrame({ multiHandLandmarks: [], poseLandmarks: null }, 0)).toEqual({ t: 0, pose: null, lh: null, rh: null, face: null })
  })

  it('remembers the switch in the browser, on by default', () => {
    const m = new Map()
    const storage = { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v) }
    expect(cloudSaveEnabled(storage)).toBe(true)
    setCloudSaveEnabled(false, storage)
    expect(m.get(CLOUD_SAVE_KEY)).toBe('off')
    expect(cloudSaveEnabled(storage)).toBe(false)
    setCloudSaveEnabled(true, storage)
    expect(cloudSaveEnabled(storage)).toBe(true)
  })

  it('picks the first video format the browser supports', () => {
    expect(pickMimeType((m) => m === 'video/webm')).toBe('video/webm')
    expect(pickMimeType(() => false)).toBe('')
  })

  it('posts the video and the track points as one form to the backend', async () => {
    const fetchImpl = vi.fn(async (url, init) => ({ ok: true, json: async () => ({ purpose: 'learning', url, method: init.method }) }))
    const video = new Blob(['x'], { type: 'video/webm' })
    const res = await uploadRecording({ purpose: 'learning', label: 'HELLO', video, skeleton: { fps: 25, frames: [{ t: 0 }] }, duration: 2.5, fps: 25, notes: 'n', width: 640, height: 480 }, fetchImpl)
    expect(res.method).toBe('POST')
    const [url, init] = fetchImpl.mock.calls[0]
    expect(url).toMatch(/\/cloud\/recordings$/)
    expect(init.credentials).toBe('include')
    const form = init.body
    expect(form.get('purpose')).toBe('learning')
    expect(form.get('label')).toBe('HELLO')
    expect(form.get('duration')).toBe('2.5')
    expect(JSON.parse(form.get('skeleton'))).toEqual({ fps: 25, frames: [{ t: 0 }] })
    expect(form.get('video')).toBeInstanceOf(Blob)
    await expect(uploadRecording({ purpose: 'nope', label: 'x' }, fetchImpl)).rejects.toThrow(/unknown purpose/)
    const failing = vi.fn(async () => ({ ok: false, status: 502, json: async () => ({ detail: 'Supabase is not reachable' }) }))
    await expect(uploadRecording({ purpose: 'learning', label: 'x', skeleton: { frames: [{ t: 0 }] } }, failing)).rejects.toThrow(/not reachable/)
  })
})
