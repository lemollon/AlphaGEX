'use client'

import { useEffect, useRef, useState } from 'react'
import { US_STATES } from '@/lib/us-states'
import { CAPITAL_RANGES, CONSENT_COPY, validateWaitlistClient } from '@/lib/waitlist'
import { useWaitlistModal } from '@/components/marketing/WaitlistModal'
import { track } from '@/lib/analytics/track'

/**
 * 10.4 restyle (gap audit "Waitlist as in-page modal" PARTIAL/L + 3 copy/behavior
 * items flagged PARTIAL/MISSING below) — same fields and the same
 * `POST /api/waitlist` contract as before, rebuilt against the design's own
 * `.sheet`/`.field`/`.cap`/`.check` classes (forge-marketing.css, mechanically
 * derived from the design CSS) instead of a bespoke dark/amber Tailwind form.
 */

type Form = {
  firstName: string; lastName: string; email: string; phone: string
  city: string; state: string; tradingCapitalRange: string; communicationConsent: boolean
}
const EMPTY: Form = {
  firstName: '', lastName: '', email: '', phone: '',
  city: '', state: '', tradingCapitalRange: '', communicationConsent: false,
}

/** Live mask while typing, e.g. "(555) 555-0123" (design spec §2 "Waitlist modal"
 *  — previously PARTIAL: a plain `type="tel"` text field with no mask). */
function formatPhoneDisplay(raw: string): string {
  const d = raw.replace(/\D/g, '').slice(0, 10)
  if (d.length === 0) return ''
  if (d.length < 4) return `(${d}`
  if (d.length < 7) return `(${d.slice(0, 3)}) ${d.slice(3)}`
  return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`
}

/**
 * The waitlist form card itself (fields, validation, submit, success state) — pulled
 * out of the page body so the SAME component renders both at the standalone /waitlist
 * route (kept working for direct links and bookmarks) and inside the site-wide
 * waitlist modal (ps-ctas "Join the waitlist -> Opens waitlist modal, no navigation").
 */
export function WaitlistForm() {
  const { placement } = useWaitlistModal()
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

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (busy) return
    setServerError(null)
    const clientErrs = validateWaitlistClient(form)
    if (Object.keys(clientErrs).length > 0) {
      setErrors(clientErrs)
      track('waitlist_error', { placement, field: Object.keys(clientErrs)[0] })
      return
    }
    setBusy(true)
    try {
      const res = await fetch('/api/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, company: '', campaign: campaignRef.current }), // company = honeypot
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.ok) {
        track('waitlist_submit', { placement, capitalRange: form.tradingCapitalRange })
        setDone({ existing: Boolean(data.existing) })
        return
      }
      if (res.status === 422 && data.fieldErrors) {
        setErrors(data.fieldErrors)
        track('waitlist_error', { placement, field: Object.keys(data.fieldErrors)[0] })
        return
      }
      setServerError(data.message || 'We could not save your request. Please try again.')
      track('waitlist_error', { placement, field: 'server' })
    } catch {
      // Network failure: retain values, offer retry (handoff §3).
      setServerError('Network error — your details are still here. Please try again.')
      track('waitlist_error', { placement, field: 'network' })
    } finally {
      setBusy(false)
    }
  }

  // Design spec §2 "Waitlist modal": "If capital < $5K, mention Ember" (previously
  // MISSING entirely).
  const showEmberNote = form.tradingCapitalRange === 'under_5000'

  return (
    <div className="card" style={{ overflow: 'hidden' }}>
            {done ? (
              <div className="success" style={{ justifyItems: 'center', textAlign: 'center' }}>
                <span className="ok">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <use href="#i-check" />
                  </svg>
                </span>
                <h2>You&rsquo;re on the list.</h2>
                <p className="muted">
                  {done.existing
                    ? 'Your waitlist details have been updated. We’ll email you as launch approaches.'
                    : 'Thanks for joining. Check your inbox for a confirmation — we’ll keep you posted as we get closer to launch.'}
                </p>
              </div>
            ) : (
              <div className="sheet-body">
                {serverError ? <p className="err" style={{ marginBottom: 14 }}>{serverError}</p> : null}

                <form onSubmit={onSubmit} noValidate>
                  {/* honeypot */}
                  <input type="text" name="company" tabIndex={-1} autoComplete="off" aria-hidden
                    value="" onChange={() => {}} style={{ display: 'none' }} />

                  <div className="group">Contact information</div>
                  <div className="row2">
                    <div className="field">
                      <label htmlFor="firstName">First name<span className="req"> *</span></label>
                      <input ref={firstRef} id="firstName" placeholder="Enter your first name"
                        value={form.firstName} onChange={(e) => set('firstName', e.target.value)} />
                      <p className="err">{errors.firstName}</p>
                    </div>
                    <div className="field">
                      <label htmlFor="lastName">Last name<span className="req"> *</span></label>
                      <input id="lastName" placeholder="Enter your last name"
                        value={form.lastName} onChange={(e) => set('lastName', e.target.value)} />
                      <p className="err">{errors.lastName}</p>
                    </div>
                    <div className="field">
                      <label htmlFor="email">Email<span className="req"> *</span></label>
                      <input id="email" type="email" placeholder="Enter your email address"
                        value={form.email} onChange={(e) => set('email', e.target.value)} />
                      <p className="err">{errors.email}</p>
                    </div>
                    <div className="field">
                      <label htmlFor="phone">Phone<span className="req"> *</span></label>
                      <input id="phone" type="tel" inputMode="tel" placeholder="(555) 555-0123"
                        value={form.phone} onChange={(e) => set('phone', formatPhoneDisplay(e.target.value))} />
                      <p className="err">{errors.phone}</p>
                    </div>
                  </div>

                  <div className="group">Location</div>
                  <div className="row2">
                    <div className="field">
                      <label htmlFor="city">City<span className="req"> *</span></label>
                      <input id="city" placeholder="Enter your city"
                        value={form.city} onChange={(e) => set('city', e.target.value)} />
                      <p className="err">{errors.city}</p>
                    </div>
                    <div className="field">
                      <label htmlFor="state">State<span className="req"> *</span></label>
                      <select id="state" value={form.state} onChange={(e) => set('state', e.target.value)}>
                        <option value="">Select your state</option>
                        {US_STATES.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
                      </select>
                      <p className="err">{errors.state}</p>
                    </div>
                  </div>

                  <div className="group">Trading profile</div>
                  <fieldset>
                    <legend>How much capital do you expect to actively trade?<span className="req"> *</span></legend>
                    <div className="caps">
                      {CAPITAL_RANGES.map((r) => (
                        <label key={r.value} className="cap">
                          <input type="radio" name="capital" value={r.value}
                            checked={form.tradingCapitalRange === r.value}
                            onChange={() => set('tradingCapitalRange', r.value)} />
                          <span>{r.label}</span>
                        </label>
                      ))}
                    </div>
                    <p className="err">{errors.tradingCapitalRange}</p>
                    {showEmberNote ? (
                      <p className="muted" style={{ fontSize: '.86rem', marginTop: 8 }}>
                        Starting smaller? <b>Ember</b> is IronForge&rsquo;s free agent, built for $500–$2,000
                        accounts and first-time investors.
                      </p>
                    ) : null}
                  </fieldset>

                  <label className="check" style={{ marginTop: 10 }}>
                    <input type="checkbox" checked={form.communicationConsent}
                      onChange={(e) => set('communicationConsent', e.target.checked)} />
                    <span>{CONSENT_COPY}<span className="req"> *</span></span>
                  </label>
                  <p className="err">{errors.communicationConsent}</p>

                  <button type="submit" disabled={busy} className="btn btn-accent btn-block btn-lg" style={{ marginTop: 6 }}>
                    {busy ? 'Joining…' : 'Join the waitlist'}
                  </button>
                  <p className="muted" style={{ fontSize: '.8rem', textAlign: 'center', marginTop: 4 }}>
                    Options trading involves risk, including loss of money invested.
                  </p>
                </form>
              </div>
            )}
    </div>
  )
}

/** The standalone /waitlist page body (ps-ctas: the page itself must keep working
 *  for direct links and bookmarks, even though every in-site CTA now opens the modal
 *  instead — see WaitlistModal.tsx). */
export default function WaitlistClient() {
  return (
    <>
      <div className="wrap page-head">
        <h1>Join the waitlist</h1>
        <p>Be the first to know when IronForge opens the next onboarding wave.</p>
      </div>

      <section className="sec">
        <div className="wrap" style={{ maxWidth: 680, marginInline: 'auto' }}>
          <WaitlistForm />
        </div>
      </section>
    </>
  )
}
