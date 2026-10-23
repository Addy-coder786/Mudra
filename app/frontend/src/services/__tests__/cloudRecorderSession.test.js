import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { CloudRecorder } from '../cloudRecorder'

const result = (x) => ({ multiHandLandmarks: [Array.from({ length: 21 }, () => ({ x, y: 0.5, z: 0 }))], multiHandedness: [{ label: 'Left', score: 1 }], poseLandmarks: null, width: 640, height: 480 })

describe('CloudRecorder session', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('collects track points between start and stop, with the clip timing, and nothing else', () => {
    const rec = new CloudRecorder()
    expect(rec.active).toBe(false)
    rec.addFrame(result(0.1)) // before start: ignored
    rec.start()
    expect(rec.active).toBe(true)
    for (let i = 0; i < 3; i++) { vi.advanceTimersByTime(40); rec.addFrame(result(0.2 + i * 0.1)) }
    const out = rec.stop()
    expect(Object.keys(out).sort()).toEqual(['duration', 'fps', 'height', 'skeleton', 'width'])
    expect(out.skeleton.frames).toHaveLength(3)
    expect(out.skeleton.frames[0].rh[0].x).toBeCloseTo(0.2)
    expect(out.skeleton.frames[2].t).toBeGreaterThanOrEqual(out.skeleton.frames[0].t)
    expect(out.width).toBe(640)
    expect(rec.active).toBe(false)
    expect(rec.stop()).toBeNull() // nothing to stop twice
    expect(typeof MediaRecorder).toBe('undefined') // the test runs without one: the recorder never needs it
  })
})
