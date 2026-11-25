import { useEffect, useRef, useState } from 'react'
import type { FormEvent, Ref } from 'react'
import { Eye, EyeOff, LoaderCircle } from 'lucide-react'
import { Link, Navigate } from 'react-router'
import { ApiError } from '../api/client.ts'
import type { Credentials } from '../api/types.ts'
import { useAuth } from '../hooks/auth.ts'
import { useRouteNotice } from '../hooks/notices.ts'
import { AuthLayout } from './AuthLayout.tsx'
import { Notice } from './Notice.tsx'

type AuthFields = Credentials & { confirmation: string }
type Errors = Partial<Record<keyof AuthFields, string>>

const emailAtom = "[a-z0-9!#$%&'*+/=?^_\x60{|}~-]+"
const domainLabel = '[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
const emailAddress = new RegExp(`^${emailAtom}(?:\\.${emailAtom})*@(?:${domainLabel}\\.)+${domainLabel}$`, 'i')
const authErrors: Record<string, string> = {
  invalid_credentials: 'Email or password is incorrect.',
  rate_limited: 'Too many attempts. Try again in a minute.',
  email_taken: 'An account with this email already exists.',
}

function validate(signup: boolean, { email, password, confirmation }: AuthFields): Errors {
  const errors: Errors = {}
  const address = email.trim()
  if (!emailAddress.test(address) || address.length > 254 || address.split('@')[0].length > 64) {
    errors.email = 'Enter a valid email address.'
  }
  if (!password) errors.password = 'Enter your password.'
  else if (signup && Array.from(password).length < 8) errors.password = 'Use at least 8 characters.'
  else if (signup && new TextEncoder().encode(password).length > 72) errors.password = 'Use at most 72 UTF-8 bytes.'
  if (signup && !confirmation) errors.confirmation = 'Confirm your password.'
  else if (signup && password !== confirmation) errors.confirmation = 'Passwords must match.'
  return errors
}

const strengthLabels = ['Weak', 'Fair', 'Good', 'Strong']

function PasswordStrength({ password }: { password: string }) {
  const length = Array.from(password).length
  const variety = [length >= 12, /[a-z]/.test(password) && /[A-Z]/.test(password),
    /\d/.test(password), /[^\p{L}\p{N}\s]/u.test(password)].filter(Boolean).length
  const level = !length ? 0 : length < 8 ? 1 : Math.min(4, 1 + variety)
  const label = level ? 'Password strength: ' + strengthLabels[level - 1].toLowerCase() : 'Use at least 8 characters.'
  return <div className="password-strength" id="password-strength">
    <div className="strength-segments" data-level={level} aria-hidden="true">
      {strengthLabels.map((name, index) => <span key={name} data-filled={index < level} />)}
    </div>
    <p className="secondary-text muted">{label}</p>
  </div>
}

function PasswordField({ id, value, error, busy, change, fieldRef, signup }: {
  id: 'password' | 'confirmation'
  value: string
  error?: string
  busy: boolean
  change: (value: string) => void
  fieldRef: Ref<HTMLInputElement>
} & ({ id: 'password'; signup: boolean } | { id: 'confirmation'; signup?: true })) {
  const [visible, setVisible] = useState(false)
  const confirmation = id === 'confirmation'
  const label = confirmation ? 'Confirm password' : 'Password'
  const describedBy = [error && id + '-error', id === 'password' && signup && 'password-strength'].filter(Boolean).join(' ')

  return <div className="field">
    <label htmlFor={id}>{label}</label>
    <div className="password-field">
      <input id={id} ref={fieldRef} className="input" type={visible ? 'text' : 'password'}
        disabled={busy} autoComplete={signup ? 'new-password' : 'current-password'} value={value}
        onChange={(event) => change(event.currentTarget.value)} aria-invalid={Boolean(error)}
        aria-describedby={describedBy || undefined} />
      <button className="icon-button password-toggle" type="button" disabled={busy}
        onClick={() => setVisible(!visible)}
        aria-label={(visible ? 'Hide ' : 'Show ') + (confirmation ? 'password confirmation' : 'password')}>
        {visible ? <EyeOff /> : <Eye />}
      </button>
    </div>
    {error && <p className="field-error" id={id + '-error'}>{error}</p>}
    {signup && !confirmation && <PasswordStrength password={value} />}
  </div>
}

export function AuthPage({ mode }: { mode: 'login' | 'signup' }) {
  const auth = useAuth()
  const [notice, setNotice] = useRouteNotice()
  const [values, setValues] = useState<AuthFields>({ email: '', password: '', confirmation: '' })
  const [errors, setErrors] = useState<Errors>({})
  const [failure, setFailure] = useState<{ message: string; code?: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [welcome, setWelcome] = useState<string>()
  const request = useRef<AbortController | null>(null)
  const email = useRef<HTMLInputElement>(null)
  const password = useRef<HTMLInputElement>(null)
  const confirmation = useRef<HTMLInputElement>(null)
  const signup = mode === 'signup'

  useEffect(() => {
    email.current?.focus()
    return () => request.current?.abort()
  }, [])

  if (welcome) return <Navigate to="/" state={{ message: 'Signed in to PolicyDesk RAG as ' + welcome }} replace />
  if (auth.status === 'ready' && !busy) return <Navigate to="/" replace />

  function change(field: keyof AuthFields, value: string) {
    setValues((current) => ({ ...current, [field]: value }))
    setErrors((current) => ({ ...current, [field]: undefined, ...(field === 'password' && { confirmation: undefined }) }))
    setFailure(null)
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (request.current || auth.status === 'pending') return
    const invalid = validate(signup, values)
    setErrors(invalid)
    const invalidField = invalid.email ? email : invalid.password ? password : invalid.confirmation ? confirmation : null
    if (invalidField) {
      invalidField.current?.focus()
      return
    }

    const controller = new AbortController()
    request.current = controller
    setBusy(true)
    setFailure(null)
    try {
      const user = await auth.authenticate(mode, { email: values.email.trim(), password: values.password }, controller.signal)
      setWelcome(user.email)
    } catch (error) {
      if (!controller.signal.aborted) {
        setFailure(error instanceof ApiError
          ? { code: error.code, message: authErrors[error.code] ?? error.message }
          : { message: signup ? 'Could not create your account. Please try again.' : 'Could not sign in. Please try again.' })
      }
    } finally {
      request.current = null
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  return <AuthLayout>
    <div className="auth-intro">
      <h1>{signup ? 'Create your account' : 'Welcome back'}</h1>
      <p className="muted">{signup ? 'Start asking questions about your documents.' : 'Sign in to your workspace.'}</p>
    </div>
    <form noValidate onSubmit={(event) => { void submit(event) }} className="auth-form" aria-busy={busy}>
      <div className="field">
        <label htmlFor="email">Email</label>
        <input id="email" ref={email} className="input" type="email" autoComplete="email" disabled={busy}
          value={values.email} onChange={(event) => change('email', event.currentTarget.value)}
          aria-invalid={Boolean(errors.email)} aria-describedby={errors.email ? 'email-error' : undefined} />
        {errors.email && <p className="field-error" id="email-error">{errors.email}</p>}
      </div>
      <PasswordField id="password" fieldRef={password} signup={signup} value={values.password}
        error={errors.password} busy={busy} change={(value) => change('password', value)} />
      {signup && <PasswordField id="confirmation" fieldRef={confirmation} signup value={values.confirmation}
        error={errors.confirmation} busy={busy} change={(value) => change('confirmation', value)} />}
      {failure && <p className="auth-error" role="alert">
        {failure.message}{failure.code === 'email_taken' && <> <Link to="/login" className="text-link">Sign in</Link></>}
      </p>}
      <button type="submit" className="button primary auth-submit" disabled={busy || auth.status === 'pending'}>
        {busy && <LoaderCircle className="busy-spinner" aria-hidden="true" />}
        {busy ? signup ? 'Creating account…' : 'Signing in…' : signup ? 'Create account' : 'Sign in'}
      </button>
    </form>
    <p className="auth-alternate muted">
      {signup ? 'Already have an account?' : 'New here?'}{' '}
      <Link to={signup ? '/login' : '/signup'} className="text-link">{signup ? 'Sign in' : 'Create an account'}</Link>
    </p>
    {notice && <Notice notice={notice} dismiss={() => setNotice(null)} />}
  </AuthLayout>
}
