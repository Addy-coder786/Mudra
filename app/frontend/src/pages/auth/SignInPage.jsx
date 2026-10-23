import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import Button from '../../components/ui/Button'
import { useSession } from '../../context/SessionContext'
import { startGoogleSignIn } from '../../services/googleSignIn'
import { sessionFromGoogle } from '../../services/session'
import { API_BASE_URL } from '../../services/signRecognizer'
import AuthLayout from './AuthLayout'
import { Field } from './fields'

const ERRORS = {
  google_not_configured: 'Google sign-in is not set up on this server.',
  google_cancelled: 'Google sign-in was cancelled or could not be verified.',
  google_failed: 'Google sign-in could not be completed.',
}

/**
 * Google first; a learner who cannot finish Google sign-in (not set up, cancelled, failed) is signed in locally
 * at once (services/session.js). The admin workspace needs an approved Google account, so it never falls back.
 */
export default function SignInPage() {
  const [params] = useSearchParams()
  const role = params.get('role') === 'admin' ? 'admin' : 'user'
  const { signIn, refresh, googleConfigured } = useSession()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(ERRORS[params.get('error')] || '')
  const cancelRef = useRef(null)
  const next = role === 'admin' ? '/admin' : '/app/home'

  useEffect(() => () => cancelRef.current?.(), [])

  const enter = (session) => navigate(session.role === 'admin' ? '/admin' : '/app/home', { replace: true })
  const continueLocally = (why) => {
    if (role === 'admin') { setError(`${why} Admin access needs an approved Google account.`); return }
    signIn('user', name)
    navigate('/app/home', { replace: true })
  }
  // Google ran in this tab (popup blocked) and sent the learner back here with its result: continue locally
  const returnedError = params.get('error')
  useEffect(() => {
    if (role === 'user' && returnedError && ERRORS[returnedError]) continueLocally(ERRORS[returnedError])
  }, [returnedError]) // eslint-disable-line react-hooks/exhaustive-deps
  const handleGoogle = () => {
    if (busy) return
    if (googleConfigured === false) { continueLocally(ERRORS.google_not_configured); return }
    setBusy(true)
    setError('')
    cancelRef.current = startGoogleSignIn({
      apiBase: API_BASE_URL,
      next,
      onResult: async (result) => {
        cancelRef.current = null
        setBusy(false)
        if (result.status === 'success') {
          const me = await refresh()
          const session = sessionFromGoogle(me?.user || result.user)
          if (session) { enter(session); return }
        }
        continueLocally(ERRORS[`google_${result.status}`] || ERRORS.google_failed)
      },
    })
  }

  return (
    <AuthLayout
      title={role === 'admin' ? 'Admin sign in' : 'Sign in to SignLine'}
      subtitle={role === 'admin' ? 'Admin access is limited to approved Google accounts.' : 'Continue with your Google account, or just with a name.'}
    >
      {error && <p role="alert" className="rounded-sl border-2 border-rose-700 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-800">{error}</p>}
      <Button size="lg" className="w-full" variant={role === 'admin' ? 'purple' : 'primary'} onClick={handleGoogle} disabled={busy}>
        <span aria-hidden="true" className="grid h-6 w-6 place-items-center rounded-full bg-white font-extrabold text-[#4285F4]">G</span>
        {busy ? 'Waiting for Google…' : 'Continue with Google'}
      </Button>
      {busy && <p className="text-sm text-sl-ink-600" aria-live="polite">Finish signing in in the Google window. If it does not open, allow pop-ups for this site.</p>}
      {role === 'user' && (
        <form noValidate className="space-y-4 border-t-2 border-dashed border-sl-cream-300 pt-5"
              onSubmit={(e) => { e.preventDefault(); continueLocally('') }}>
          <p className="text-sm font-semibold text-sl-ink">Or continue without Google</p>
          <Field label="Display name" autoComplete="nickname" value={name} hint="Only used to greet you in this browser."
                 onChange={(e) => setName(e.target.value)} />
          <Button type="submit" size="lg" variant="outline" className="w-full" disabled={busy}>Continue as a learner</Button>
        </form>
      )}
      <div className="flex flex-wrap justify-between gap-2 text-sm">
        <Link to="/welcome" className="font-semibold underline underline-offset-4">← Choose another role</Link>
        {role === 'user' && <Link to="/register" className="font-semibold underline underline-offset-4">Create a learner profile</Link>}
      </div>
    </AuthLayout>
  )
}
