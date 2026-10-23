import { Cloud, CloudOff } from 'lucide-react'

/**
 * The cloud-save switch and its state for a camera page (features/cloud/useCloudRecorder.js): what will happen to
 * the recording is always visible next to the camera controls, and one tap turns it off.
 */
export default function CloudSaveBadge({ cloud, className = '', dark = false }) {
  const { configured, enabled, state, toggle } = cloud
  const base = dark
    ? 'border-white/20 bg-black/60 text-white backdrop-blur-md'
    : 'border-sl-ink/20 bg-white text-sl-ink'
  if (configured === false) {
    return (
      <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold ${base} ${className}`} title="This server has no cloud storage configured">
        <CloudOff className="h-3.5 w-3.5" aria-hidden="true" /> Cloud save: not set up
      </span>
    )
  }
  const text = state.status === 'recording' ? 'recording' : state.status === 'uploading' ? 'uploading…'
    : state.status === 'saved' ? 'saved' : state.status === 'failed' ? 'failed' : enabled ? 'on' : 'off'
  const tone = state.status === 'failed' ? 'text-rose-500' : state.status === 'saved' ? 'text-emerald-500' : ''
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <button type="button" onClick={toggle} aria-pressed={enabled} disabled={configured === null}
              title={enabled ? 'Your video and track points are saved to the SignLine cloud. Tap to turn off.' : 'Nothing leaves this device. Tap to save recordings to the SignLine cloud.'}
              className={`inline-flex min-h-8 items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${base}`}>
        {enabled ? <Cloud className="h-3.5 w-3.5" aria-hidden="true" /> : <CloudOff className="h-3.5 w-3.5" aria-hidden="true" />}
        Cloud save: <span className={tone}>{text}</span>
      </button>
      {state.message && <span className={`text-xs ${state.status === 'failed' ? 'text-rose-600' : 'text-emerald-700'} ${dark ? 'text-white/90' : ''}`} role="status">{state.message}</span>}
    </span>
  )
}
