'use client'

import { useEffect, useRef, useState } from 'react'
import { US_STATES } from '@/lib/us-states'
import { CAPITAL_RANGES, CONSENT_COPY, validateWaitlistClient } from '@/lib/waitlist'

/* Icons (line style, matching the approved reference). currentColor + stroke. */
function Bell(p: { className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={p.className} aria-hidden><path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" strokeLinecap="round" strokeLinejoin="round" /><path d="M13.7 21a2 2 0 0 1-3.4 0" strokeLinecap="round" /></svg>
}
function Chart(p: { className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={p.className} aria-hidden><path d="M3 3v18h18" strokeLinecap="round" /><rect x="7" y="12" width="3" height="6" rx="1" /><rect x="12" y="8" width="3" height="10" rx="1" /><rect x="17" y="5" width="3" height="13" rx="1" /></svg>
}
function People(p: { className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={p.className} aria-hidden><circle cx="9" cy="8" r="3" /><path d="M3 20c0-3 3-5 6-5s6 2 6 5" strokeLinecap="round" /><path d="M16 5.5a3 3 0 0 1 0 5.5M17.5 20c0-2.2-1.2-3.8-2.5-4.6" strokeLinecap="round" /></svg>
}
function Shield(p: { className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={p.className} aria-hidden><path d="M12 3l7 3v5c0 4.4-3 8-7 10-4-2-7-5.6-7-10V6l7-3z" strokeLinejoin="round" /><path d="M9 12l2 2 4-4" strokeLinecap="round" strokeLinejoin="round" /></svg>
}
function Lock(p: { className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={p.className} aria-hidden><rect x="5" y="10.5" width="14" height="9" rx="2" /><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" /></svg>
}

const BENEFITS = [
  { icon: Bell, title: 'Priority Access', body: 'Get early access before public launch.' },
  { icon: Chart, title: 'Market Insights', body: 'Receive exclusive market intelligence and updates.' },
  { icon: People, title: 'Community First', body: 'Connect with serious traders and share strategies.' },
  { icon: Shield, title: 'No Commitment', body: 'Joining the waitlist is free and comes with no obligation.' },
]

type Form = {
  firstName: string; lastName: string; email: string; phone: string
  city: string; state: string; tradingCapitalRange: string; communicationConsent: boolean
}
const EMPTY: Form = {
  firstName: '', lastName: '', email: '', phone: '',
  city: '', state: '', tradingCapitalRange: '', communicationConsent: false,
}

const inputCls =
  'w-full rounded-lg border border-forge-border bg-black/40 px-4 py-3 text-sm text-white placeholder-gray-500 outline-none transition focus:border-amber-500'
const labelCls = 'block text-sm text-gray-200'
const req = <span className="text-amber-500"> *</span>

export default function WaitlistClient() {
  const [form, setForm] = useState<Form>(EMPTY)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)
  const [done, setDone] = useState<null | { existing: boolean }>(null)
  const firstRef = useRef<HTMLInputElement>(null)
  const campaignRef = useRef<Record<string, string>>({})

  // Capture UTM + referral + landing page once (handoff §5). The gate forwards
  // these onto /waitlist; here we read them off the URL and attach to the submit.
  useEffect(() => {
    if (typeof window === 'undefined') return
    const q = new URLSearchParams(window.location.search)
    const c: Record<string, string> = {}
    for (const k of ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term']) {
      const v = q.get(k)
      if (v) c[k] = v.slice(0, 200)
    }
    const ref = q.get('ref') || q.get('referral') || q.get('referralCode') || q.get('code')
    if (ref) c.referralCode = ref.slice(0, 200)
    c.landingPath = window.location.pathname
    campaignRef.current = c
  }, [])

  const set = (k: keyof Form, v: string | boolean) => {
    setForm((f) => ({ ...f, [k]: v }))
    setErrors((e) => (e[k] ? { ...e, [k]: '' } : e))
  }

  function scrollToForm() {
    document.getElementById('waitlist-form')?.scrollIntoView({ behavior: 'smooth' })
    setTimeout(() => firstRef.current?.focus(), 350)
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (busy) return
    setServerError(null)
    const clientErrs = validateWaitlistClient(form)
    if (Object.keys(clientErrs).length > 0) { setErrors(clientErrs); return }
    setBusy(true)
    try {
      const res = await fetch('/api/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, company: '', campaign: campaignRef.current }), // company = honeypot
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.ok) { setDone({ existing: Boolean(data.existing) }); return }
      if (res.status === 422 && data.fieldErrors) { setErrors(data.fieldErrors); return }
      setServerError(data.message || 'We could not save your request. Please try again.')
    } catch {
      // Network failure: retain values, offer retry (handoff §3).
      setServerError('Network error — your details are still here. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main>
      {/* Hero + benefits */}
      <section className="mx-auto grid max-w-[1200px] grid-cols-1 gap-10 px-5 pb-10 pt-10 md:px-8 lg:grid-cols-[6fr_5fr] lg:gap-12">
        <div>
          <span className="inline-block rounded-full border border-amber-500/60 px-4 py-1.5 text-[11px] font-bold uppercase tracking-wider text-amber-500">
            Early Access. Real Edge.
          </span>
          <h1 className="mt-6 text-[52px] font-extrabold leading-[1.02] tracking-tight text-white md:text-[64px]">
            Be <span className="text-amber-500">First.</span>
          </h1>
          <p className="mt-5 max-w-md text-[17px] leading-relaxed text-gray-300">
            IronForge is built for traders who want real strategies, real results, and real
            community. Join the waitlist to get early access.
          </p>
          <button
            type="button"
            onClick={scrollToForm}
            className="mt-7 w-full rounded-lg bg-green-500 px-6 py-4 text-[16px] font-bold text-white shadow-lg shadow-green-500/20 transition-colors hover:bg-green-400"
          >
            Join the Waitlist
          </button>
          <p className="mt-4 flex items-center gap-2 text-sm text-gray-400">
            <Lock className="h-4 w-4 shrink-0 text-amber-500" /> No commitment. Be the first to know when we launch.
          </p>
        </div>

        <aside className="rounded-2xl border border-forge-border bg-forge-card/60 p-6 md:p-7">
          <h2 className="text-lg font-bold text-white">What You’ll Get</h2>
          <ul className="mt-4 divide-y divide-forge-border">
            {BENEFITS.map(({ icon: Icon, title, body }) => (
              <li key={title} className="flex items-start gap-4 py-4">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-amber-500/40 bg-amber-500/10 text-amber-500">
                  <Icon className="h-5 w-5" />
                </span>
                <div>
                  <div className="text-[15px] font-bold text-white">{title}</div>
                  <p className="mt-0.5 text-sm leading-relaxed text-gray-400">{body}</p>
                </div>
              </li>
            ))}
          </ul>
        </aside>
      </section>

      {/* Form */}
      <section className="mx-auto max-w-[1200px] px-5 pb-16 md:px-8">
        <div id="waitlist-form" className="scroll-mt-24 rounded-2xl border border-forge-border bg-forge-card/60 p-6 md:p-9">
          {done ? (
            <div role="status" className="mx-auto max-w-md py-8 text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-green-500/40 bg-green-500/10 text-green-500">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" className="h-7 w-7"><path d="M20 6 9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </div>
              <h2 className="mt-4 text-2xl font-bold text-white">You’re on the list.</h2>
              <p className="mt-2 text-sm leading-relaxed text-gray-400">
                {done.existing
                  ? 'Your waitlist details have been updated. We’ll email you as launch approaches.'
                  : 'Thanks for joining. Check your inbox for a confirmation — we’ll keep you posted as we get closer to launch.'}
              </p>
            </div>
          ) : (
            <>
              <div className="text-center">
                <h2 className="inline-block border-b-2 border-amber-500 pb-1 text-2xl font-bold text-white">Join the Waitlist</h2>
                <p className="mt-2 text-sm text-gray-400">Secure your early access. Spots are limited.</p>
              </div>

              {serverError ? (
                <p className="mx-auto mt-5 max-w-2xl rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-center text-sm text-red-300">{serverError}</p>
              ) : null}

              <form onSubmit={onSubmit} noValidate className="mt-7 space-y-7">
                {/* honeypot */}
                <input type="text" name="company" tabIndex={-1} autoComplete="off" aria-hidden
                  value="" onChange={() => {}} className="hidden" />

                {/* Contact */}
                <div>
                  <h3 className="text-sm font-bold uppercase tracking-wide text-amber-500">Contact Information</h3>
                  <div className="mt-4 grid gap-5 md:grid-cols-2">
                    <Field id="firstName" label="First Name" required err={errors.firstName}>
                      <input ref={firstRef} id="firstName" className={inputCls} placeholder="Enter your first name"
                        value={form.firstName} onChange={(e) => set('firstName', e.target.value)} />
                    </Field>
                    <Field id="lastName" label="Last Name" required err={errors.lastName}>
                      <input id="lastName" className={inputCls} placeholder="Enter your last name"
                        value={form.lastName} onChange={(e) => set('lastName', e.target.value)} />
                    </Field>
                    <Field id="email" label="Email Address" required err={errors.email}>
                      <input id="email" type="email" className={inputCls} placeholder="Enter your email address"
                        value={form.email} onChange={(e) => set('email', e.target.value)} />
                    </Field>
                    <Field id="phone" label="Phone Number" required err={errors.phone}>
                      <input id="phone" type="tel" className={inputCls} placeholder="Enter your phone number"
                        value={form.phone} onChange={(e) => set('phone', e.target.value)} />
                    </Field>
                  </div>
                </div>

                {/* Location */}
                <div>
                  <h3 className="text-sm font-bold uppercase tracking-wide text-amber-500">Location</h3>
                  <div className="mt-4 grid gap-5 md:grid-cols-2">
                    <Field id="city" label="City" required err={errors.city}>
                      <input id="city" className={inputCls} placeholder="Enter your city"
                        value={form.city} onChange={(e) => set('city', e.target.value)} />
                    </Field>
                    <Field id="state" label="State" required err={errors.state}>
                      <div className="relative">
                        <select id="state" value={form.state} onChange={(e) => set('state', e.target.value)}
                          className={`${inputCls} appearance-none pr-10 ${form.state ? '' : 'text-gray-500'}`}>
                          <option value="">Select your state</option>
                          {US_STATES.map((s) => <option key={s.code} value={s.code} className="text-white">{s.name}</option>)}
                        </select>
                        <svg viewBox="0 0 20 20" fill="none" className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500"><path d="M6 8l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
                      </div>
                    </Field>
                  </div>
                </div>

                {/* Trading profile */}
                <div>
                  <h3 className="text-sm font-bold uppercase tracking-wide text-amber-500">Trading Profile</h3>
                  <p className="mt-3 text-sm text-gray-200">How much capital do you expect to actively trade?{req}</p>
                  <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
                    {CAPITAL_RANGES.map((r) => {
                      const active = form.tradingCapitalRange === r.value
                      return (
                        <label key={r.value}
                          className={`flex min-h-[56px] cursor-pointer items-center gap-3 rounded-lg border px-4 py-3 text-sm transition ${
                            active ? 'border-amber-500 bg-amber-500/10 text-white' : 'border-forge-border bg-black/30 text-gray-300 hover:border-white/25'
                          }`}>
                          <input type="radio" name="capital" value={r.value} checked={active}
                            onChange={() => set('tradingCapitalRange', r.value)} className="sr-only" />
                          <span aria-hidden className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${active ? 'border-amber-500' : 'border-gray-500'}`}>
                            {active ? <span className="h-2 w-2 rounded-full bg-amber-500" /> : null}
                          </span>
                          <span className="leading-tight">{r.label}</span>
                        </label>
                      )
                    })}
                  </div>
                  {errors.tradingCapitalRange ? <p className="mt-2 text-xs text-red-400">{errors.tradingCapitalRange}</p> : null}
                </div>

                {/* Consent */}
                <div>
                  <label className="flex items-start gap-3 text-sm text-gray-300">
                    <input type="checkbox" checked={form.communicationConsent}
                      onChange={(e) => set('communicationConsent', e.target.checked)}
                      className="mt-0.5 h-5 w-5 shrink-0 rounded border-forge-border bg-black/40 accent-amber-500" />
                    <span>{CONSENT_COPY}{req}</span>
                  </label>
                  {errors.communicationConsent ? <p className="mt-1.5 pl-8 text-xs text-red-400">{errors.communicationConsent}</p> : null}
                </div>

                <button type="submit" disabled={busy}
                  className="w-full rounded-lg bg-green-500 px-6 py-4 text-[16px] font-bold text-white shadow-lg shadow-green-500/20 transition-colors hover:bg-green-400 disabled:cursor-not-allowed disabled:opacity-60">
                  {busy ? 'Joining…' : 'Join the Waitlist'}
                </button>
                <p className="flex items-center justify-center gap-2 text-xs text-gray-500">
                  <Lock className="h-3.5 w-3.5 text-gray-500" /> We respect your privacy. Your information will never be shared.
                </p>
              </form>
            </>
          )}
        </div>
      </section>
    </main>
  )
}

function Field({ id, label, required, err, children }: {
  id: string; label: string; required?: boolean; err?: string; children: React.ReactNode
}) {
  return (
    <div>
      <label htmlFor={id} className={labelCls}>{label}{required ? req : null}</label>
      <div className="mt-1.5">{children}</div>
      {err ? <p className="mt-1.5 text-xs text-red-400">{err}</p> : null}
    </div>
  )
}
