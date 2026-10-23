import { useState } from 'react'
import { Link } from 'react-router-dom'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import { useAccessibility } from '../context/AccessibilityContext'
import { useSession } from '../context/SessionContext'
import { resetProgress } from '../features/game/progress'
import { API_BASE_URL } from '../services/signRecognizer'

function Toggle({ label, help, checked, onChange }) {
  return (
    <label className="flex items-start justify-between gap-4 py-3">
      <span>
        <span className="block font-bold">{label}</span>
        {help && <span className="block text-sm text-sl-ink-600">{help}</span>}
      </span>
      <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)}
             className="mt-1 h-6 w-6 shrink-0 accent-sl-green" />
    </label>
  )
}

/** Accessibility and data settings (shared by the User and Admin workspaces). */
export default function SettingsPage({ admin = false }) {
  const a = useAccessibility()
  const { session } = useSession()
  const [confirming, setConfirming] = useState(false)
  const [done, setDone] = useState('')

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-6 pb-24 sm:px-6 lg:py-10">
      <header>
        <p className={`text-sm font-bold uppercase tracking-wider ${admin ? 'text-sl-purple-700' : 'text-sl-green-700'}`}>{admin ? 'Admin' : 'Settings'}</p>
        <h1 className="font-display text-4xl font-extrabold tracking-tight">Settings</h1>
        <p className="mt-2 text-sl-ink-600">Saved in this browser only.</p>
      </header>

      <Card className="divide-y divide-sl-cream-300 px-5">
        <h2 className="py-3 font-display text-xl font-bold">Accessibility</h2>
        <div className="py-3">
          <p className="font-bold">Text size</p>
          <div role="radiogroup" aria-label="Text size" className="mt-2 flex flex-wrap gap-2">
            {[['normal', 'Normal'], ['large', 'Large'], ['xlarge', 'Extra large']].map(([v, t]) => (
              <button key={v} type="button" role="radio" aria-checked={a.fontSize === v} onClick={() => a.setFontSize(v)}
                      className={`min-h-11 rounded-full border-2 border-sl-ink px-4 font-bold ${a.fontSize === v ? 'bg-sl-ink text-white' : 'bg-white'}`}>
                {t}
              </button>
            ))}
          </div>
        </div>
        <Toggle label="High contrast" help="Stronger colours and outlines." checked={a.highContrast} onChange={a.setHighContrast} />
        <Toggle label="Reduce motion" help="Turns off animations (also follows your system setting)." checked={a.reducedMotion} onChange={a.setReducedMotion} />
        <div className="py-3">
          <label className="block font-bold" htmlFor="speech-rate">Speech speed: {a.speechRate.toFixed(1)}×</label>
          <input id="speech-rate" type="range" min="0.5" max="1.5" step="0.1" value={a.speechRate}
                 onChange={(e) => a.setSpeechRate(Number(e.target.value))} className="mt-2 w-full accent-sl-green" />
          <p className="text-sm text-sl-ink-600">Used when SignLine speaks recognised sentences.</p>
        </div>
      </Card>

      {!admin && (
        <Card className="space-y-3 p-5">
          <h2 className="font-display text-xl font-bold">Your data</h2>
          <p className="text-sm text-sl-ink-600">
            Game Mode progress for “{session?.name}” is stored in this browser. Signs you record on Customize your sign are stored on the
            SignLine server and can be deleted there.
          </p>
          {!confirming ? (
            <Button variant="outline" onClick={() => setConfirming(true)}>Reset my Game Mode progress</Button>
          ) : (
            <div role="alertdialog" aria-label="Confirm reset" className="space-y-3 rounded-sl border-2 border-rose-700 bg-rose-50 p-4">
              <p className="font-bold">Delete all XP, lessons, streak and badges for “{session?.name}”? This cannot be undone.</p>
              <div className="flex gap-2">
                <Button variant="dark" onClick={() => { resetProgress(session?.name); setConfirming(false); setDone('Progress reset. Reload pages to see it.') }}>Yes, reset</Button>
                <Button variant="outline" onClick={() => setConfirming(false)}>Cancel</Button>
              </div>
            </div>
          )}
          {done && <p role="status" className="text-sm font-semibold text-sl-sun-700">✓ {done}</p>}
        </Card>
      )}

      <Card className="space-y-2 p-5 text-sm">
        <h2 className="font-display text-xl font-bold">About</h2>
        <p>Recognition server: <code className="rounded bg-sl-cream-200 px-1">{API_BASE_URL}</code></p>
        <p>Sign-in: demo only (no accounts).</p>
        <p className="flex flex-wrap gap-x-4 gap-y-1 pt-2">
          {[['terms', 'Terms'], ['privacy', 'Privacy'], ['accessibility', 'Accessibility statement'], ['cookies', 'Cookies and storage'],
            ['data-rights', 'Your data rights'], ['licences', 'Open-source licences'], ['contact', 'Contact']].map(([d, t]) => (
            <Link key={d} to={`/legal/${d}`} className="font-bold underline underline-offset-4">{t}</Link>
          ))}
        </p>
      </Card>
    </div>
  )
}
