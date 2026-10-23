import { useCallback, useEffect, useRef, useState } from 'react'
import { CloudRecorder, cloudSaveEnabled, getCloudStatus, setCloudSaveEnabled, uploadRecording } from '../../services/cloudRecorder'

/**
 * Cloud copy of one camera session's track points (services/cloudRecorder.js) for a page: `begin()` after the
 * camera starts, `frame(results)` for every tracker result, `finish({label, notes})` when the session ends
 * (uploads the landmarks; never video), `cancel()` to drop it. `on` is true only when the server has cloud storage and the person has
 * not switched it off (`toggle`). `state.status`: idle | recording | uploading | saved | failed.
 */
export function useCloudRecorder(purpose) {
  const rec = useRef(null)
  if (!rec.current) {
    rec.current = new CloudRecorder()
    if (import.meta.env?.DEV && typeof window !== 'undefined') window.__cloudRecorder = rec.current // dev diagnostics only
  }
  const [configured, setConfigured] = useState(null)
  const [enabled, setEnabled] = useState(() => cloudSaveEnabled())
  const [state, setState] = useState({ status: 'idle', message: '' })
  const on = configured === true && enabled
  const onRef = useRef(on)
  onRef.current = on

  useEffect(() => {
    let alive = true
    getCloudStatus().then((s) => { if (alive) setConfigured(Boolean(s?.configured)) })
    return () => { alive = false; rec.current.stop() }
  }, [])

  const begin = useCallback(() => {
    if (!onRef.current) return
    rec.current.start()
    setState({ status: 'recording', message: '' })
  }, [])

  const frame = useCallback((results) => { rec.current.addFrame(results) }, [])

  const cancel = useCallback(() => {
    rec.current.stop()
    setState({ status: 'idle', message: '' })
  }, [])

  const finish = useCallback(async ({ label, notes = '' } = {}) => {
    const data = rec.current.stop()
    if (!data || !onRef.current || !data.skeleton.frames.length) {
      setState({ status: 'idle', message: '' })
      return null
    }
    setState({ status: 'uploading', message: '' })
    try {
      const res = await uploadRecording({ purpose, label, notes, ...data })
      setState({ status: 'saved', message: `${res.skeleton?.frames ?? data.skeleton.frames.length} frames of track points saved to the cloud (no video)` })
      return res
    } catch (err) {
      setState({ status: 'failed', message: err.message || 'Cloud save failed' })
      return null
    }
  }, [purpose])

  const toggle = useCallback(() => {
    setEnabled((v) => { setCloudSaveEnabled(!v); return !v })
  }, [])

  return { configured, enabled, on, state, begin, frame, finish, cancel, toggle }
}
