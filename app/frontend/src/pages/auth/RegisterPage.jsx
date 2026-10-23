import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Button from '../../components/ui/Button'
import { useSession } from '../../context/SessionContext'
import AuthLayout from './AuthLayout'
import { EMAIL_RE, Field } from './fields'

export default function RegisterPage() {
  const { signIn } = useSession()
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', password: '', accept: false })
  const [errors, setErrors] = useState({})

  const submit = (e) => {
    e.preventDefault()
    const err = {}
    if (!form.name.trim()) err.name = 'Enter the name SignLine should show.'
    if (!EMAIL_RE.test(form.email.trim())) err.email = 'Enter an email address like name@example.com.'
    if (form.password.length < 8) err.password = 'Use at least 8 characters.'
    if (!form.accept) err.accept = 'Please accept the Terms and the Privacy Policy to continue.'
    setErrors(err)
    if (Object.keys(err).length) return
    signIn('user', form.name) // learner profiles only: registering never creates an admin
    navigate('/app/home', { replace: true })
  }

  return (
    <AuthLayout title="Create a learner profile" subtitle="Only what SignLine needs: a name to greet you.">
      <form noValidate onSubmit={submit} className="space-y-4">
        <Field label="Display name" autoComplete="nickname" value={form.name} error={errors.name}
               onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <Field label="Email" type="email" autoComplete="email" value={form.email} error={errors.email}
               onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <Field label="Password" type="password" autoComplete="new-password" value={form.password} error={errors.password}
               hint="At least 8 characters." onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <div>
          <label className="flex items-start gap-3 text-sm text-sl-ink">
            <input
              type="checkbox"
              checked={form.accept}
              onChange={(e) => setForm({ ...form, accept: e.target.checked })}
              aria-invalid={errors.accept ? 'true' : undefined}
              className="mt-0.5 h-5 w-5 rounded border-2 border-sl-ink accent-sl-green"
            />
            <span>
              I accept the <Link to="/legal/terms" className="font-bold underline underline-offset-4">Terms and Conditions</Link> and
              the <Link to="/legal/privacy" className="font-bold underline underline-offset-4">Privacy Policy</Link>.
            </span>
          </label>
          {errors.accept && <p className="mt-1 text-sm font-semibold text-rose-700">⚠ {errors.accept}</p>}
        </div>
        <Button type="submit" size="lg" className="w-full">Create profile</Button>
      </form>
      <p className="text-sm">
        Already have one? <Link to="/signin?role=user" className="font-semibold underline underline-offset-4">Sign in</Link>
      </p>
    </AuthLayout>
  )
}
