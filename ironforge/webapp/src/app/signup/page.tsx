'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { US_STATES } from '@/lib/us-states'
import { Wordmark } from '@/components/Brand'
import {
  checkPassword,
  validateSignup,
  type SignupPayload,
} from '@/lib/signup-validation'

/* ── Inline glyphs (custom SVG, no emojis/stock icons) ─────────────── */

const iconBase = 'h-4 w-4'

function ShieldGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
      <path d="M12 3l7 3v5c0 4.2-2.9 7.4-7 8.5-4.1-1.1-7-4.3-7-8.5V6l7-3z" stroke="#EE5A24" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M9 12l2 2 4-4.2" stroke="#EE5A24" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function BoltGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
      <path d="M13 2L4 14h6l-1 8 9-12h-6l1-8z" stroke="#EE5A24" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  )
}

function BarsGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
      <path d="M5 20V11M12 20V4M19 20v-6" stroke="#EE5A24" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

function UserIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={iconBase} aria-hidden="true">
      <circle cx="12" cy="8" r="3.2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M5.5 19a6.5 6.5 0 0113 0" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}
function MailIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={iconBase} aria-hidden="true">
      <rect x="3.5" y="5.5" width="17" height="13" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M4 7l8 6 8-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}
function PhoneIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={iconBase} aria-hidden="true">
      <path d="M6.5 3.5h3l1.5 4-2 1.5a11 11 0 005 5l1.5-2 4 1.5v3a2 2 0 01-2 2C10 21.5 2.5 14 2.5 5.5a2 2 0 012-2z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  )
}
function LocationIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={iconBase} aria-hidden="true">
      <path d="M12 21s6-5.3 6-10a6 6 0 10-12 0c0 4.7 6 10 6 10z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <circle cx="12" cy="11" r="2.2" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}
function LockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={iconBase} aria-hidden="true">
      <rect x="5" y="10.5" width="14" height="9" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 10.5V8a4 4 0 018 0v2.5" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}
function TagIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={iconBase} aria-hidden="true">
      <path d="M3.5 11.5l8-8H20v8.5l-8 8-8.5-8.5z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <circle cx="15.5" cy="8.5" r="1.3" fill="currentColor" />
    </svg>
  )
}
function EyeIcon({ off }: { off?: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={iconBase} aria-hidden="true">
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <circle cx="12" cy="12" r="2.6" stroke="currentColor" strokeWidth="1.5" />
      {off && <path d="M4 4l16 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />}
    </svg>
  )
}
function CheckTick({ ok }: { ok: boolean }) {
  return (
    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 shrink-0" aria-hidden="true">
      {ok ? (
        <path d="M3 8.5l3 3 7-7.5" stroke="#EE5A24" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      ) : (
        <circle cx="8" cy="8" r="2.2" fill="#52525b" />
      )}
    </svg>
  )
}

function HomeGlyph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true">
      <path d="M4 11l8-7 8 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6 10v9h12v-9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10 19v-5h4v5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** Always-available link back to the home page. */
function HomeLink({ className = '' }: { className?: string }) {
  return (
    <Link
      href="/"
      className={`inline-flex items-center gap-1.5 font-medium text-gray-400 transition hover:text-amber-400 ${className}`}
    >
      <HomeGlyph />
      Home
    </Link>
  )
}

/* ── Field primitives ──────────────────────────────────────────────── */

interface FieldProps {
  id: keyof SignupPayload
  label: string
  type?: string
  placeholder?: string
  value: string
  icon: React.ReactNode
  error?: string
  autoComplete?: string
  onChange: (v: string) => void
  trailing?: React.ReactNode
}

function Field({ id, label, type = 'text', placeholder, value, icon, error, autoComplete, onChange, trailing }: FieldProps) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-xs font-medium text-gray-300">{label}</label>
      <div className="relative">
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">{icon}</span>
        <input
          id={id}
          name={id}
          type={type}
          autoComplete={autoComplete}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={!!error}
          className={`w-full rounded-md bg-black/40 border px-9 py-2.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-1 ${
            error ? 'border-red-600/70 focus:border-red-500 focus:ring-red-500' : 'border-white/10 focus:border-amber-500 focus:ring-amber-500'
          }`}
        />
        {trailing && <span className="absolute right-2.5 top-1/2 -translate-y-1/2">{trailing}</span>}
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}

/* ── Page ──────────────────────────────────────────────────────────── */

const PASSWORD_RULE_LABELS: Array<{ key: keyof ReturnType<typeof checkPassword>['rules']; label: string }> = [
  { key: 'minLength', label: 'At least 12 characters' },
  { key: 'upper', label: 'An uppercase letter' },
  { key: 'lower', label: 'A lowercase letter' },
  { key: 'number', label: 'A number' },
  { key: 'special', label: 'A special character' },
]

const EMPTY: SignupPayload = {
  firstName: '', lastName: '', email: '', phone: '', state: '',
  password: '', confirmPassword: '', referralCode: '',
  ageConfirmed: false, noAdviceAcknowledged: false, electronicCommConsent: false,
}

export default function SignupPage() {
  const [form, setForm] = useState<SignupPayload>(EMPTY)
  const [errors, setErrors] = useState<Partial<Record<keyof SignupPayload, string>>>({})
  const [showPw, setShowPw] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null)

  const set = (k: keyof SignupPayload, v: string | boolean) => {
    setForm((f) => ({ ...f, [k]: v }))
    setErrors((e) => (e[k] ? { ...e, [k]: undefined } : e))
  }

  const pwRules = useMemo(() => checkPassword(form.password).rules, [form.password])

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setServerError(null)
    const result = validateSignup(form)
    if (!result.ok) {
      setErrors(result.errors)
      return
    }
    setSubmitting(true)
    try {
      const res = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(form),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        if (data.fields) setErrors(data.fields)
        setServerError(data.error || 'Something went wrong creating your account. Please try again.')
        return
      }
      setSubmittedEmail(result.normalized.email)
    } catch {
      setServerError('Something went wrong creating your account. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (submittedEmail) {
    return <VerifyEmailShell email={submittedEmail} />
  }

  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-8 sm:py-12">
      <div className="mx-auto max-w-5xl">
        <div className="mb-4 flex items-center justify-between text-sm text-gray-400">
          <HomeLink />
          <span>
            Already have an account?{' '}
            <Link href="/login" className="font-semibold text-amber-500 hover:text-amber-400">Log in</Link>
          </span>
        </div>

        <div className="grid overflow-hidden rounded-2xl border border-white/10 bg-forge-card/60 shadow-2xl lg:grid-cols-[0.85fr_1fr]">
          {/* Left brand panel */}
          <aside className="relative hidden flex-col justify-between gap-10 border-r border-white/10 bg-gradient-to-b from-black/40 to-black/10 p-8 lg:flex">
            <div>
              <Wordmark />
              <h2 className="mt-10 text-2xl font-bold leading-tight text-white">
                Automated<br />Options<br />Execution
              </h2>
              <div className="fire-divider my-5 w-16" />
              <p className="max-w-xs text-sm leading-relaxed text-gray-400">
                Rules-based strategies. Automated execution. Built for traders who demand an edge.
              </p>
            </div>

            <ul className="space-y-5">
              <Feature glyph={<ShieldGlyph />} title="Secure & Transparent" body="Bank-grade security and total transparency." />
              <Feature glyph={<BoltGlyph />} title="Automated Execution" body="Systematic strategies executed 24/7." />
              <Feature glyph={<BarsGlyph />} title="You Stay in Control" body="You authorize. We execute. You decide." />
            </ul>

            <p className="text-[11px] leading-relaxed text-gray-600">
              IronForge is not a broker dealer and does not provide investment advice.
            </p>
          </aside>

          {/* Right form card */}
          <div className="bg-forge-card/90 p-6 sm:p-8">
            <h1 className="text-2xl font-bold text-white">Create your account</h1>
            <p className="mt-2 text-sm leading-relaxed text-gray-400">
              Start your setup for automated options execution. You will review disclosures, connect billing, and authorize your brokerage before anything is activated.
            </p>
            <div className="fire-divider my-5" />

            <form onSubmit={onSubmit} noValidate className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field id="firstName" label="First Name" placeholder="First Name" icon={<UserIcon />} autoComplete="given-name" value={form.firstName} error={errors.firstName} onChange={(v) => set('firstName', v)} />
                <Field id="lastName" label="Last Name" placeholder="Last Name" icon={<UserIcon />} autoComplete="family-name" value={form.lastName} error={errors.lastName} onChange={(v) => set('lastName', v)} />
              </div>

              <Field id="email" label="Email Address" type="email" placeholder="name@email.com" icon={<MailIcon />} autoComplete="email" value={form.email} error={errors.email} onChange={(v) => set('email', v)} />
              <Field id="phone" label="Mobile Phone" type="tel" placeholder="(555) 123-4567" icon={<PhoneIcon />} autoComplete="tel" value={form.phone} error={errors.phone} onChange={(v) => set('phone', v)} />

              {/* State select */}
              <div className="space-y-1">
                <label htmlFor="state" className="block text-xs font-medium text-gray-300">State of Residence</label>
                <div className="relative">
                  <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"><LocationIcon /></span>
                  <select
                    id="state"
                    name="state"
                    value={form.state}
                    onChange={(e) => set('state', e.target.value)}
                    aria-invalid={!!errors.state}
                    className={`w-full appearance-none rounded-md bg-black/40 border px-9 py-2.5 text-sm focus:outline-none focus:ring-1 ${
                      errors.state ? 'border-red-600/70 focus:border-red-500 focus:ring-red-500' : 'border-white/10 focus:border-amber-500 focus:ring-amber-500'
                    } ${form.state ? 'text-gray-100' : 'text-gray-500'}`}
                  >
                    <option value="" disabled>Select your state</option>
                    {US_STATES.map((s) => (
                      <option key={s.code} value={s.code} className="text-gray-100">{s.name}</option>
                    ))}
                  </select>
                  <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">
                    <svg viewBox="0 0 16 16" className="h-4 w-4" aria-hidden="true"><path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
                  </span>
                </div>
                {errors.state && <p className="text-xs text-red-400">{errors.state}</p>}
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field
                  id="password" label="Password" type={showPw ? 'text' : 'password'} placeholder="Create a strong password"
                  icon={<LockIcon />} autoComplete="new-password" value={form.password} error={errors.password} onChange={(v) => set('password', v)}
                  trailing={<button type="button" onClick={() => setShowPw((s) => !s)} className="text-gray-500 hover:text-gray-300" aria-label={showPw ? 'Hide password' : 'Show password'}><EyeIcon off={showPw} /></button>}
                />
                <Field
                  id="confirmPassword" label="Confirm Password" type={showConfirm ? 'text' : 'password'} placeholder="Confirm your password"
                  icon={<LockIcon />} autoComplete="new-password" value={form.confirmPassword} error={errors.confirmPassword} onChange={(v) => set('confirmPassword', v)}
                  trailing={<button type="button" onClick={() => setShowConfirm((s) => !s)} className="text-gray-500 hover:text-gray-300" aria-label={showConfirm ? 'Hide password' : 'Show password'}><EyeIcon off={showConfirm} /></button>}
                />
              </div>

              {/* Live password rule checklist */}
              {form.password.length > 0 && (
                <ul className="grid grid-cols-1 gap-1 rounded-md border border-white/5 bg-black/20 p-3 sm:grid-cols-2">
                  {PASSWORD_RULE_LABELS.map((r) => (
                    <li key={r.key} className={`flex items-center gap-1.5 text-xs ${pwRules[r.key] ? 'text-gray-300' : 'text-gray-500'}`}>
                      <CheckTick ok={pwRules[r.key]} />
                      {r.label}
                    </li>
                  ))}
                </ul>
              )}

              <Field id="referralCode" label="Referral Code (Optional)" placeholder="Enter referral code" icon={<TagIcon />} value={form.referralCode || ''} error={errors.referralCode} onChange={(v) => set('referralCode', v)} />

              {/* Consent checkboxes */}
              <div className="space-y-3 pt-1">
                <Consent checked={form.ageConfirmed} error={errors.ageConfirmed} onChange={(v) => set('ageConfirmed', v)}>
                  I am at least 18 years old and legally able to open and manage a brokerage account.
                </Consent>
                <Consent checked={form.noAdviceAcknowledged} error={errors.noAdviceAcknowledged} onChange={(v) => set('noAdviceAcknowledged', v)}>
                  I understand IronForge provides automated trade execution technology and{' '}
                  <span className="font-medium text-amber-500">does not provide financial, investment, tax, or legal advice</span>.
                </Consent>
                <Consent checked={form.electronicCommConsent} error={errors.electronicCommConsent} onChange={(v) => set('electronicCommConsent', v)}>
                  I agree to receive <span className="font-medium text-amber-500">electronic communications</span> related to my account, billing, legal notices, and platform activity.
                </Consent>
              </div>

              {serverError && (
                <p className="rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-xs text-red-300">{serverError}</p>
              )}

              <button
                type="submit"
                disabled={submitting}
                className="flex w-full items-center justify-center gap-2 rounded-md bg-amber-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <ShieldSmall />
                {submitting ? 'Creating account…' : 'Create Account'}
              </button>

              <p className="flex items-center justify-center gap-1.5 text-center text-[11px] text-gray-500">
                <LockSmall />
                Your information is secure. We use bank-level encryption to protect your data.
              </p>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}

function Feature({ glyph, title, body }: { glyph: React.ReactNode; title: string; body: string }) {
  return (
    <li className="flex items-start gap-3">
      <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-amber-900/40 bg-amber-950/20">{glyph}</span>
      <div>
        <p className="text-sm font-semibold text-white">{title}</p>
        <p className="text-xs text-gray-400">{body}</p>
      </div>
    </li>
  )
}

function Consent({ checked, error, onChange, children }: { checked: boolean; error?: string; onChange: (v: boolean) => void; children: React.ReactNode }) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5 text-xs leading-relaxed text-gray-400">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className={`mt-0.5 h-4 w-4 shrink-0 rounded border bg-black/40 accent-amber-600 ${error ? 'border-red-600' : 'border-white/20'}`}
      />
      <span>{children}</span>
    </label>
  )
}

function ShieldSmall() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true">
      <path d="M12 3l7 3v5c0 4.2-2.9 7.4-7 8.5-4.1-1.1-7-4.3-7-8.5V6l7-3z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M9 12l2 2 4-4.2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
function LockSmall() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-3.5 w-3.5" aria-hidden="true">
      <rect x="5" y="10.5" width="14" height="9" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 10.5V8a4 4 0 018 0v2.5" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  )
}

/* ── Screen 2: Verify email ─────────────────────────────────────────── */

function VerifyEmailShell({ email }: { email: string }) {
  const [status, setStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')

  async function resend() {
    setStatus('sending')
    try {
      const res = await fetch('/api/auth/resend-verification', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      setStatus(res.ok ? 'sent' : 'error')
    } catch {
      setStatus('error')
    }
  }

  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-16">
      <div className="mx-auto max-w-md rounded-2xl border border-white/10 bg-forge-card/90 p-8 text-center shadow-2xl">
        <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full border border-amber-900/40 bg-amber-950/20">
          <svg viewBox="0 0 24 24" fill="none" className="h-7 w-7" aria-hidden="true">
            <rect x="3.5" y="5.5" width="17" height="13" rx="2" stroke="#EE5A24" strokeWidth="1.6" />
            <path d="M4 7l8 6 8-6" stroke="#EE5A24" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </div>
        <h1 className="text-xl font-bold text-white">Verify your email</h1>
        <p className="mt-2 text-sm text-gray-400">We sent a verification link to:</p>
        <p className="mt-1 text-sm font-semibold text-amber-500">{email}</p>
        <p className="mt-3 text-sm text-gray-400">Confirm your email to continue setup.</p>

        <button
          type="button"
          onClick={resend}
          disabled={status === 'sending' || status === 'sent'}
          className="mt-6 w-full rounded-md border border-white/10 bg-black/30 px-4 py-2.5 text-sm font-medium text-gray-300 transition hover:bg-black/50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {status === 'sending' ? 'Sending…' : status === 'sent' ? 'Verification email sent' : 'Resend Verification Email'}
        </button>
        {status === 'error' && (
          <p className="mt-2 text-xs text-red-400">Could not resend right now. Please try again shortly.</p>
        )}

        <p className="mt-4 text-xs text-gray-500">
          Already verified?{' '}
          <Link href="/login" className="font-semibold text-amber-500 hover:text-amber-400">Continue</Link>
        </p>

        <div className="mt-6 flex justify-center border-t border-white/5 pt-4 text-sm">
          <HomeLink />
        </div>
      </div>
    </div>
  )
}
