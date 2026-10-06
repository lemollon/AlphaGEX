'use client'

import { useEffect } from 'react'
import Link from 'next/link'
import { Wordmark } from '@/components/Brand'
import { trackEnrollStepView } from '@/lib/analytics/enroll'
import type { EnrollPageStep } from './steps'
import type { EnrollmentSummary } from './useEnrollment'

/**
 * 10.4 enrollment chrome (handoff .claude/handoff/ironforge-10.4-redesign.md +
 * ironforge-10.4-design-spec.md §5): step rail on the left (clickable only on
 * completed steps), one focused task in the middle, a running "Your setup"
 * summary on the right — same visual system as the public site, scoped under
 * `.if-enroll` (src/styles/forge-enroll.css) so it never touches marketing.
 *
 * ORDER (10/5 reorder, Leron): Create account -> Agreements -> Choose agent ->
 * Connect brokerage -> Billing -> Review & enter — the exact rail order and titles
 * from IronForge_Enrollment_10.4.html. Account creation (/signup, now also reachable
 * at /enroll/account) is step 1 of the rail; billing is an embedded Stripe Elements
 * form (src/app/enroll/billing/StripeCardForm.tsx), not a hosted-Checkout redirect,
 * falling back to the old redirect only when no publishable key is configured. This
 * is a WEB-ONLY rail — the mobile app keeps its own existing order over the same API
 * (see lib/enrollment/service.ts resolveNextStepWeb vs nextStepFor).
 *
 * At narrow widths the rail collapses to a thin progress bar (`.mprog`) and the
 * side summary hides — same breakpoints as the design CSS.
 */

const RAIL: Array<{ step: EnrollPageStep; label: string; sub: string }> = [
  { step: 'account', label: 'Create account', sub: 'Your login' },
  { step: 'legal', label: 'Agreements', sub: 'Review and sign' },
  { step: 'plan', label: 'Choose agent', sub: 'Spark, Flame, Ember or Community' },
  { step: 'broker', label: 'Connect brokerage', sub: 'Tradier and more' },
  { step: 'billing', label: 'Billing', sub: 'Secured by Stripe' },
  { step: 'review', label: 'Review & enter', sub: 'Final check' },
]

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  )
}

export default function EnrollShell({
  headline,
  subline,
  topRight = 'save-exit',
  maxWidthClass = 'max-w-2xl',
  step,
  enrollment,
  children,
}: {
  headline: string
  subline?: string
  /** 'login' before an account exists (ACCT-01); 'save-exit' once enrollment is resumable. */
  topRight?: 'save-exit' | 'login' | 'none'
  maxWidthClass?: string
  /** Which rail item is current. Omit on screens outside the 6-step rail (e.g. done). */
  step?: EnrollPageStep
  /** Feeds the "Your setup" side summary — pass the enrollment each step already loads. */
  enrollment?: EnrollmentSummary | null
  children: React.ReactNode
}) {
  // en-events: fires once per step mount, paired with trackEnrollStepComplete()
  // called by whichever client component owns that step's "Continue" action.
  useEffect(() => {
    if (step) trackEnrollStepView(step)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step])

  const railIndex = step ? RAIL.findIndex((r) => r.step === step) : -1
  const progressPct = railIndex >= 0 ? Math.round(((railIndex + 1) / RAIL.length) * 100) : 0
  // en-5 #126: "Ember skips this step; the rail shows 'Not needed for Ember.'"
  // Billing is skipped entirely for Ember (service.ts isEmberPlan) — the rail
  // sub-label says so instead of the generic "Secured by Stripe".
  const isEmber = enrollment?.selected_plan === 'ember'
  const rail = isEmber ? RAIL.map((r) => (r.step === 'billing' ? { ...r, sub: 'Not needed for Ember' } : r)) : RAIL

  return (
    <div className="if-enroll">
      <header className="top">
        <div className="top-in">
          <Link href="/" aria-label="IronForge home"><Wordmark markClass="h-6 w-auto" textClass="text-base" /></Link>
          {topRight === 'login' ? (
            <span className="secure">
              Already have an account? <Link href="/login" className="link" style={{ textDecoration: 'none', color: 'var(--accent-text)' }}>Log in</Link>
            </span>
          ) : null}
          {topRight === 'save-exit' ? (
            // State is server-persisted after every step, so "Save & exit" is a plain
            // link — resuming later re-enters at the earliest incomplete gate.
            <span className="secure">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                <rect x="4" y="10" width="16" height="10" rx="2" />
                <path d="M8 10V7a4 4 0 0 1 8 0v3" />
              </svg>
              <span className="t">Your progress is saved</span>
              <Link href="/home" className="link" style={{ textDecoration: 'none', marginLeft: 10 }}>Save &amp; exit</Link>
            </span>
          ) : null}
        </div>
        {/* Mobile progress bar — replaces the rail below 780px. */}
        {railIndex >= 0 ? (
          <div className="mprog"><i style={{ width: `${progressPct}%` }} /></div>
        ) : null}
      </header>

      <div className="shell">
        {railIndex >= 0 ? (
          <nav className="rail" aria-label="Enrollment steps">
            <div className="rail-h">Setting up IronForge</div>
            {rail.map((r, i) => {
              const state = i < railIndex ? 'done' : i === railIndex ? 'cur' : 'skip'
              const content = (
                <>
                  <span className="dot" aria-hidden="true">
                    {state === 'done' ? <CheckIcon /> : i + 1}
                  </span>
                  <span>
                    {r.label}
                    <small>{r.sub}</small>
                  </span>
                </>
              )
              return state === 'done' ? (
                <Link key={r.step} href={`/enroll/${r.step}`} className={`rs ${state}`}>
                  {content}
                </Link>
              ) : (
                <div key={r.step} className={`rs ${state}`} aria-current={state === 'cur' ? 'step' : undefined}>
                  {content}
                </div>
              )
            })}
          </nav>
        ) : null}

        <div className={`panel ${maxWidthClass}`}>
          <div className="step-h">
            <h1>{headline}</h1>
            {subline ? <p>{subline}</p> : null}
          </div>
          {children}
        </div>

        {railIndex >= 0 ? (
          <aside className="side">
            <div className="card pad">
              <div className="rail-h" style={{ marginBottom: 12 }}>Your setup</div>
              <div className="sum-row">
                <span>Plan</span>
                <b className="num">{enrollment?.selected_plan ? enrollment.selected_plan[0].toUpperCase() + enrollment.selected_plan.slice(1) : '—'}</b>
              </div>
              <div className="sum-row">
                <span>Step</span>
                <b>{railIndex + 1} of {RAIL.length}</b>
              </div>
            </div>
            <div className="card pad help-card">
              <b>Your money stays in your account.</b>
              <p>IronForge sends trade instructions through your broker and can never withdraw or transfer funds.</p>
              <b>Card data is never stored by IronForge.</b>
              <p>Billing is handled directly by Stripe.</p>
            </div>
          </aside>
        ) : null}
      </div>
    </div>
  )
}
