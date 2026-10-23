import { useMemo, useState } from 'react'
import { Search, Trash2 } from 'lucide-react'
import Button from '../../components/ui/Button'
import Card from '../../components/ui/Card'
import StatusPill from '../../components/ui/StatusPill'
import { CURRICULUM } from '../../features/game/curriculum'
import { BADGES, LESSONS, RULES, dayKey } from '../../features/game/progress'
import { TIPS } from '../../features/game/quiz'
import { VOCABULARY_SIZE } from '../../features/vocabulary'
import { ISL_VOCABULARY_LEXICON } from '../../services/islDictionary'
import { getJson, localProfiles, useApi } from './adminData'

export function AdminHeader({ title, children }) {
  return (
    <header>
      <p className="text-sm font-bold uppercase tracking-wider text-sl-purple-700">Admin</p>
      <h1 className="font-display text-4xl font-extrabold tracking-tight">{title}</h1>
      {children && <div className="mt-2 max-w-3xl text-sl-ink-600">{children}</div>}
    </header>
  )
}

const page = 'mx-auto max-w-6xl space-y-6 px-4 py-6 pb-24 sm:px-6 lg:py-10'
const th = 'py-2 pr-4 text-left text-xs font-bold uppercase tracking-wide text-sl-ink-600'
const td = 'py-2 pr-4 align-top'

function Pager({ page: p, pages, onPage }) {
  if (pages <= 1) return null
  return (
    <div className="flex items-center justify-end gap-2 text-sm">
      <Button size="sm" variant="outline" disabled={p === 0} onClick={() => onPage(p - 1)}>Previous</Button>
      <span>Page {p + 1} of {pages}</span>
      <Button size="sm" variant="outline" disabled={p >= pages - 1} onClick={() => onPage(p + 1)}>Next</Button>
    </div>
  )
}

function ApiState({ api, children }) {
  if (api.status === 'loading') return <p role="status" className="text-sl-ink-600">Loading…</p>
  if (api.status === 'error') return <p className="text-rose-700">⚠ Could not reach the SignLine server ({api.error}). <button className="underline" type="button" onClick={api.reload}>Retry</button></p>
  return children
}

// ------------------------------------------------------------------------------------------- Users
export function AdminUsersPage() {
  const profiles = useMemo(localProfiles, [])
  return (
    <div className={page}>
      <AdminHeader title="Users">
        There are no accounts: sign-in is a demo. The only learner data that exists is Game Mode progress saved in each
        browser, so this page can show the demo profiles of <strong>this browser</strong> only. Account management (roles,
        suspension, deletion) needs real accounts and is not available.
      </AdminHeader>
      <Card className="p-5">
        <div className="flex items-center gap-2">
          <h2 className="font-display text-xl font-bold">Demo profiles in this browser</h2>
          <StatusPill status="demo">This browser only</StatusPill>
        </div>
        {profiles.length === 0 ? (
          <p className="mt-3 text-sm text-sl-ink-600">No Game Mode progress has been saved in this browser yet.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="border-b-2 border-sl-ink"><tr><th className={th}>Name</th><th className={th}>XP</th><th className={th}>Lessons passed</th><th className={th}>Words</th><th className={th}>Badges</th><th className={th}>Last lesson</th></tr></thead>
              <tbody>
                {profiles.map((p) => (
                  <tr key={p.name} className="border-b border-sl-cream-300">
                    <td className={`${td} font-semibold`}>{p.name}</td><td className={td}>{p.xp}</td><td className={td}>{p.passed} / {p.total}</td>
                    <td className={td}>{p.words}</td><td className={td}>{p.badges}</td><td className={td}>{p.lastAt ? new Date(p.lastAt).toLocaleString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}

// ----------------------------------------------------------------------------------------- Content
export function AdminContentPage() {
  const labels = useApi('/labels')
  const [q, setQ] = useState('')
  const [p, setP] = useState(0)
  const rows = (labels.data?.labels || []).filter((l) => !q || l.label.toLowerCase().includes(q.toLowerCase()))
  const per = 25
  return (
    <div className={page}>
      <AdminHeader title="Learning content">
        What learners see comes from three real sources, all read-only here: the model’s vocabulary (with one recorded
        example per word), the Game Mode curriculum in the app code, and the avatar lexicon. Editing, drafts and publishing
        need a content store on the server, which does not exist yet.
      </AdminHeader>
      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="p-5"><p className="text-sm font-semibold text-sl-ink-600">Model vocabulary</p><p className="font-display text-3xl font-extrabold">{labels.data ? VOCABULARY_SIZE : '—'}</p><StatusPill status={labels.status === 'live' ? 'live' : 'unavailable'} /></Card>
        <Card className="p-5"><p className="text-sm font-semibold text-sl-ink-600">Game Mode lessons</p><p className="font-display text-3xl font-extrabold">{LESSONS.length}</p><p className="text-xs text-sl-ink-600">{CURRICULUM.length} sections · in code (features/game/curriculum.js)</p></Card>
        <Card className="p-5"><p className="text-sm font-semibold text-sl-ink-600">Avatar lexicon</p><p className="font-display text-3xl font-extrabold">{ISL_VOCABULARY_LEXICON.length}</p><p className="text-xs text-sl-ink-600">Descriptions not yet checked by an ISL signer</p></Card>
      </div>
      <Card className="space-y-3 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-xl font-bold">Vocabulary</h2>
          <label className="relative">
            <span className="sr-only">Search vocabulary</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2" aria-hidden="true" />
            <input value={q} onChange={(e) => { setQ(e.target.value); setP(0) }} placeholder="Search…" className="min-h-10 rounded-full border-2 border-sl-ink pl-9 pr-3" />
          </label>
        </div>
        <ApiState api={labels}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead className="border-b-2 border-sl-ink"><tr><th className={th}>Word</th><th className={th}>Recorded example</th><th className={th}>Held-out test (same signers)</th><th className={th}>Lesson</th></tr></thead>
              <tbody>
                {rows.slice(p * per, p * per + per).map((l) => {
                  const lesson = LESSONS.find((x) => x.words.includes(l.sign))
                  return (
                    <tr key={l.sign} className="border-b border-sl-cream-300">
                      <td className={`${td} font-semibold`}>{l.label}</td>
                      <td className={td}>{l.has_reference ? 'Yes' : 'No'}</td>
                      <td className={td}>{l.test_clips ? `${l.test_correct} of ${l.test_clips}` : '—'}</td>
                      <td className={td}>{lesson ? `${lesson.unitTitle} ${lesson.number}` : '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <Pager page={p} pages={Math.ceil(rows.length / per)} onPage={setP} />
        </ApiState>
      </Card>
    </div>
  )
}

// ----------------------------------------------------------------------------------------- Records
export function AdminRecordsPage() {
  const recs = useApi('/recordings')
  const events = useApi('/events?limit=2000')
  const [confirm, setConfirm] = useState(null)
  const [msg, setMsg] = useState('')
  const [kind, setKind] = useState('sign_ended')
  const [status, setStatus] = useState('all')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [p, setP] = useState(0)
  const per = 25

  const remove = async (item) => {
    try {
      await getJson(`/recordings/${item.sample_id}`, { method: 'DELETE' })
      setMsg(`Deleted recording ${item.sample_id} (${item.label}).`)
      recs.reload()
    } catch (e) {
      setMsg(`Could not delete: ${e.message}`)
    }
    setConfirm(null)
  }

  const evs = (events.data?.events || []).filter((e) =>
    (kind === 'all' || e.event === kind) && (status === 'all' || e.status === status) &&
    (!from || (e.time || '') >= from) && (!to || (e.time || '').slice(0, 10) <= to))

  return (
    <div className={page}>
      <AdminHeader title="Records">
        Real server records: signs recorded on Customize your sign (landmarks only, no video) and the live recognition log (one
        line per detected sign; no landmarks). There are no account, lesson or audit records on the server yet.
      </AdminHeader>
      {msg && <p role="status" className="rounded-sl border-2 border-sl-ink bg-white p-3 text-sm font-semibold">{msg}</p>}

      <Card className="space-y-3 p-5">
        <div className="flex items-center gap-2"><h2 className="font-display text-xl font-bold">Recorded signs</h2><StatusPill status={recs.status === 'live' ? 'live' : 'unavailable'} /></div>
        <ApiState api={recs}>
          {recs.data?.total === 0 ? <p className="text-sm text-sl-ink-600">No recordings yet.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px] text-sm">
                <thead className="border-b-2 border-sl-ink"><tr><th className={th}>Word</th><th className={th}>Recorded by</th><th className={th}>Length</th><th className={th}>Hands visible</th><th className={th}>Quality</th><th className={th}><span className="sr-only">Actions</span></th></tr></thead>
                <tbody>
                  {(recs.data?.signs || []).flatMap((s) => s.items).map((it) => (
                    <tr key={it.sample_id} className="border-b border-sl-cream-300">
                      <td className={`${td} font-semibold`}>{it.label}</td><td className={td}>{it.signer}</td><td className={td}>{it.duration_s.toFixed(1)} s</td>
                      <td className={td}>{Math.round(it.any_hand_rate * 100)}%</td><td className={td}>{it.quality_flag || 'OK'}</td>
                      <td className={td}>
                        <Button size="sm" variant="outline" onClick={() => setConfirm(it)} aria-label={`Delete recording of ${it.label} by ${it.signer}`}>
                          <Trash2 className="h-4 w-4" aria-hidden="true" /> Delete
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </ApiState>
        {confirm && (
          <div role="alertdialog" aria-label="Confirm delete" className="space-y-3 rounded-sl border-2 border-rose-700 bg-rose-50 p-4">
            <p className="font-bold">Delete the recording of “{confirm.label}” by {confirm.signer}? Its landmark file is removed and it stops counting as a personal example. This cannot be undone.</p>
            <div className="flex gap-2"><Button variant="dark" onClick={() => remove(confirm)}>Yes, delete</Button><Button variant="outline" onClick={() => setConfirm(null)}>Cancel</Button></div>
          </div>
        )}
      </Card>

      <Card className="space-y-3 p-5">
        <div className="flex items-center gap-2"><h2 className="font-display text-xl font-bold">Recognition log</h2><StatusPill status={events.status === 'live' ? 'live' : 'unavailable'} /></div>
        <div className="flex flex-wrap gap-3 text-sm">
          <label className="flex items-center gap-2">Type
            <select value={kind} onChange={(e) => { setKind(e.target.value); setP(0) }} className="min-h-10 rounded-full border-2 border-sl-ink px-3">
              <option value="sign_ended">Signs</option><option value="too_short">Too short</option><option value="client_diag">Camera diagnostics</option><option value="all">All</option>
            </select>
          </label>
          <label className="flex items-center gap-2">Result
            <select value={status} onChange={(e) => { setStatus(e.target.value); setP(0) }} className="min-h-10 rounded-full border-2 border-sl-ink px-3">
              <option value="all">All</option><option value="ok">Added</option><option value="uncertain">Uncertain</option><option value="no_sign">No sign</option><option value="duplicate">Duplicate</option>
            </select>
          </label>
          <label className="flex items-center gap-2">From <input type="date" value={from} onChange={(e) => { setFrom(e.target.value); setP(0) }} className="min-h-10 rounded-full border-2 border-sl-ink px-3" /></label>
          <label className="flex items-center gap-2">To <input type="date" value={to} onChange={(e) => { setTo(e.target.value); setP(0) }} className="min-h-10 rounded-full border-2 border-sl-ink px-3" /></label>
        </div>
        <ApiState api={events}>
          <p className="text-xs text-sl-ink-600">{evs.length} matching entries (of the latest {events.data?.events.length}; {events.data?.total} in the log). Newest first.</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="border-b-2 border-sl-ink"><tr><th className={th}>Time</th><th className={th}>Event</th><th className={th}>Result</th><th className={th}>Top guess</th><th className={th}>Length / fps</th><th className={th}>Ended by</th></tr></thead>
              <tbody>
                {evs.slice(p * per, p * per + per).map((e, i) => (
                  <tr key={`${e.time}-${i}`} className="border-b border-sl-cream-300">
                    <td className={td}>{e.time}</td><td className={td}>{e.event}</td>
                    <td className={td}>{e.event === 'client_diag' ? `${e.tracking_fps ?? '?'} fps tracking · ${e.delegate ?? '?'}` : (e.status || '—')}{e.sign ? `: ${e.sign}` : ''}</td>
                    <td className={td}>{e.top?.[0] ? `${e.top[0][0]} (${Math.round(e.top[0][1] * 100)}%)` : '—'}</td>
                    <td className={td}>{e.duration_s != null ? `${e.duration_s} s` : '—'}{e.fps ? ` · ${e.fps} fps` : ''}</td>
                    <td className={td}>{e.reason || (e.camera ? e.camera : '—')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager page={p} pages={Math.ceil(evs.length / per)} onPage={setP} />
        </ApiState>
      </Card>
    </div>
  )
}

// ----------------------------------------------------------------------------------------- Reports
function Bars({ data, label }) {
  const max = Math.max(1, ...data.map((d) => d.value))
  return (
    <div className="mt-4 flex h-40 items-end gap-1" role="img" aria-label={`${label}: ${data.map((d) => `${d.key} ${d.value}`).join(', ')}`}>
      {data.map((d) => (
        <div key={d.key} className="flex h-full flex-1 flex-col items-center justify-end gap-1" title={`${d.key}: ${d.value}`}>
          <div className="w-full rounded-t-md bg-sl-purple" style={{ height: `${(d.value / max) * 100}%`, minHeight: d.value ? 4 : 0 }} />
          <span className="text-[10px] text-sl-ink-600">{d.short}</span>
        </div>
      ))}
    </div>
  )
}

export function AdminReportsPage() {
  const events = useApi('/events?limit=5000')
  const signs = (events.data?.events || []).filter((e) => e.event === 'sign_ended')
  const days = useMemo(() => {
    const out = []
    for (let i = 13; i >= 0; i -= 1) {
      const d = new Date(); d.setDate(d.getDate() - i)
      const key = dayKey(d) // the log uses local time
      out.push({ key, short: key.slice(8), value: signs.filter((e) => (e.time || '').startsWith(key)).length })
    }
    return out
  }, [signs])
  const byStatus = ['ok', 'uncertain', 'no_sign', 'duplicate'].map((s) => ({ s, n: signs.filter((e) => e.status === s).length }))
  const top = Object.entries(signs.filter((e) => e.status === 'ok').reduce((acc, e) => ({ ...acc, [e.sign]: (acc[e.sign] || 0) + 1 }), {}))
    .sort((a, b) => b[1] - a[1]).slice(0, 8)
  const diag = (events.data?.events || []).filter((e) => e.event === 'client_diag')
  const avgFps = diag.length ? (diag.reduce((a, e) => a + (e.tracking_fps || 0), 0) / diag.length).toFixed(1) : null

  return (
    <div className={page}>
      <AdminHeader title="Reports">
        Summaries of the live recognition log on the server. The log does not know which word was really signed, so these
        counts describe what SignLine decided, not how accurate it was. Learning reports need accounts (not available).
      </AdminHeader>
      <ApiState api={events}>
        {signs.length === 0 ? <Card className="p-5 text-sl-ink-600">No signs have been logged yet.</Card> : (
          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="p-5"><h2 className="font-display text-lg font-bold">Detected signs, last 14 days</h2><Bars data={days} label="Detected signs per day" /></Card>
            <Card className="p-5">
              <h2 className="font-display text-lg font-bold">What SignLine decided ({signs.length} signs)</h2>
              <ul className="mt-3 space-y-2 text-sm">
                {byStatus.map(({ s, n }) => (
                  <li key={s}>
                    <div className="flex justify-between"><span className="font-semibold">{{ ok: 'Word added', uncertain: 'Uncertain', no_sign: 'No sign', duplicate: 'Duplicate' }[s]}</span><span>{n} ({Math.round((n / signs.length) * 100)}%)</span></div>
                    <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-sl-cream-200"><div className="h-full rounded-full bg-sl-green" style={{ width: `${(n / signs.length) * 100}%` }} /></div>
                  </li>
                ))}
              </ul>
            </Card>
            <Card className="p-5">
              <h2 className="font-display text-lg font-bold">Most added words</h2>
              {top.length === 0 ? <p className="mt-2 text-sm text-sl-ink-600">No word has been added yet.</p> : (
                <ol className="mt-3 space-y-1 text-sm">{top.map(([w, n]) => <li key={w} className="flex justify-between"><span>{w}</span><span>{n}</span></li>)}</ol>
              )}
            </Card>
            <Card className="p-5">
              <h2 className="font-display text-lg font-bold">Camera tracking</h2>
              {avgFps ? <p className="mt-2 text-sm">Average tracking speed over {diag.length} reports: <strong>{avgFps} fps</strong>. Below 15 fps recognition suffers.</p>
                : <p className="mt-2 text-sm text-sl-ink-600">No camera diagnostics logged yet.</p>}
            </Card>
          </div>
        )}
      </ApiState>
    </div>
  )
}

// -------------------------------------------------------------------------------------- Game rules
export function AdminGameRulesPage() {
  return (
    <div className={page}>
      <AdminHeader title="Game rules">
        The rules Game Mode uses today. They are defined in the app code (<code>src/features/game/progress.js</code>) and
        apply to every learner the same way; changing them here needs a server-side settings store (not available), so this
        page is read-only. Scores cannot be edited by admins.
      </AdminHeader>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="font-display text-lg font-bold">Points and progress</h2>
          <ul className="mt-3 space-y-1.5 text-sm">
            <li>{RULES.xpPerCorrect} XP per right answer</li>
            <li>{RULES.lessonBonus} XP bonus the first time a lesson is passed</li>
            <li>A lesson is passed with at least {Math.round(RULES.passShare * 100)}% right; passing unlocks the next one</li>
            <li>Daily goal: {RULES.dailyGoalXp} XP · a new level every {RULES.xpPerLevel} XP</li>
            <li>Streak: consecutive days with at least one lesson</li>
            <li>Leaderboard: not available (needs accounts)</li>
          </ul>
        </Card>
        <Card className="p-5">
          <h2 className="font-display text-lg font-bold">Badges</h2>
          <ul className="mt-3 space-y-1.5 text-sm">{BADGES.map((b) => <li key={b.id}><strong>{b.title}</strong> · {b.text}</li>)}</ul>
        </Card>
        <Card className="p-5 lg:col-span-2">
          <h2 className="font-display text-lg font-bold">Lesson tips</h2>
          <p className="text-sm text-sl-ink-600">Shown with new signs. General facts about sign languages and SignLine advice; review before publishing.</p>
          <ul className="mt-3 space-y-1.5 text-sm">{TIPS.map((t) => <li key={t.text}><strong>{t.kind}:</strong> {t.text}</li>)}</ul>
        </Card>
      </div>
    </div>
  )
}
