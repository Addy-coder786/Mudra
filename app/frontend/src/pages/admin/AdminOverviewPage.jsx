import { useEffect, useState } from 'react'
import { Activity, BookOpen, Database, Mic, Users } from 'lucide-react'
import Card from '../../components/ui/Card'
import StatusPill from '../../components/ui/StatusPill'
import { API_BASE_URL } from '../../services/signRecognizer'
import { VOCABULARY_SIZE } from '../../features/vocabulary'

async function getJson(path) {
  const res = await fetch(`${API_BASE_URL}${path}`)
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
  return res.json()
}

function Stat({ icon: Icon, label, value, status, note }) {
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-full border-2 border-sl-ink bg-sl-cream-100">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
        <StatusPill status={status} />
      </div>
      <p className="mt-4 text-sm font-semibold text-sl-ink-600">{label}</p>
      <p className="mt-1 font-display text-3xl font-extrabold text-sl-ink">{value}</p>
      {note && <p className="mt-2 text-xs text-sl-ink-600">{note}</p>}
    </Card>
  )
}

/** Admin overview: only numbers the backend really reports; everything else is marked unavailable. */
export default function AdminOverviewPage() {
  const [state, setState] = useState({ loading: true })

  useEffect(() => {
    let alive = true
    Promise.allSettled([getJson('/health'), getJson('/model'), getJson('/recordings')]).then(([health, model, recordings]) => {
      if (alive) setState({ loading: false, health, model, recordings })
    })
    return () => { alive = false }
  }, [])

  const ok = (r) => r?.status === 'fulfilled'
  const h = ok(state.health) ? state.health.value : null
  const m = ok(state.model) ? state.model.value : null
  const r = ok(state.recordings) ? state.recordings.value : null
  const testAcc = m?.metrics?.test?.accuracy

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 py-6 sm:px-6 lg:py-10">
      <header>
        <p className="text-sm font-bold uppercase tracking-wider text-sl-purple-700">Admin</p>
        <h1 className="font-display text-4xl font-extrabold tracking-tight text-sl-ink">Overview</h1>
        <p className="mt-2 max-w-2xl text-sl-ink-600">
          Live values come straight from the recognition server at <code className="rounded bg-sl-cream-200 px-1">{API_BASE_URL}</code>.
          SignLine has no accounts or server-side progress yet, so user and learning numbers are not available.
        </p>
      </header>

      {state.loading ? (
        <p role="status" className="text-sl-ink-600">Loading system status…</p>
      ) : (
        <section aria-label="System" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Stat icon={Activity} label="Recognition server" status={h ? (h.model_loaded ? 'live' : 'error') : 'error'}
                value={h ? (h.model_loaded ? 'Online' : 'No model') : 'Offline'}
                note={h ? `${h.model} · ${h.device}` : 'Not reachable. Start the backend (start_all.bat).'} />
          <Stat icon={BookOpen} label="Words the model knows" status={h ? 'live' : 'unavailable'}
                value={h ? VOCABULARY_SIZE : '—'}
                note={testAcc != null ? `Test clips: ${(testAcc * 100).toFixed(1)}%, from signers seen in training (not new people).` : undefined} />
          <Stat icon={Mic} label="Recorded signs (Record page)" status={r ? 'live' : 'unavailable'}
                value={r ? r.total : '—'}
                note={r ? `${r.signs.length} ${r.signs.length === 1 ? "word" : "words"} · ${r.custom_words.length} with active personal examples` : undefined} />
          <Stat icon={Users} label="Registered users" status="unavailable" value="—"
                note="No accounts exist: sign-in is a demo kept in each browser." />
        </section>
      )}

      {r && r.signs.length > 0 && (
        <Card className="p-5">
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5" aria-hidden="true" />
            <h2 className="font-display text-xl font-bold">Recorded words</h2>
            <StatusPill status="live" />
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[480px] text-left text-sm">
              <thead className="border-b-2 border-sl-ink text-xs uppercase tracking-wide text-sl-ink-600">
                <tr><th className="py-2 pr-4">Word</th><th className="py-2 pr-4">Recordings</th><th className="py-2 pr-4">Rejected</th><th className="py-2 pr-4">In model</th><th className="py-2">Personal examples</th></tr>
              </thead>
              <tbody>
                {r.signs.map((s) => (
                  <tr key={s.sign} className="border-b border-sl-cream-300">
                    <td className="py-2 pr-4 font-semibold">{s.label}</td>
                    <td className="py-2 pr-4">{s.recordings}</td>
                    <td className="py-2 pr-4">{s.rejected}</td>
                    <td className="py-2 pr-4">{s.in_model ? 'Yes' : 'No'}</td>
                    <td className="py-2">{s.custom_active ? 'Active' : 'Not yet'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
