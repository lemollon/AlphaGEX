import Link from 'next/link'
import { Wordmark } from '@/components/Brand'
import type { EnrollPageStep } from './steps'
import type { EnrollmentSummary } from './useEnrollment'

/**
 * 10.4 enrollment chrome (handoff .claude/handoff/ironforge-10.4-redesign.md +
 * ironforge-10.4-design-spec.md §5): step rail on the left (clickable only on
 * completed steps), one focused task in the middle, a running "Your setup"
 * summary on the right — same visual system as the public site, scoped under
 * `.if-enroll` (src/styles/forge-enroll.css) so it never touches marketing.
 *
 * Rail order follows this deployment's REAL flow (plan -> legal -> billing ->
 * broker -> agent -> review), not the design mock's account-first order — the
 * mock's screens don't exist 1:1 here (account creation happens at /signup
 * before /enroll even starts, and billing is hosted-Stripe-redirect, not an
 * embedded card form). Visual language matches; step sequence matches the
 * shipped funnel, since "restyle, don't change logic" rules out reordering it.
 *
 * At narrow widths the rail collapses to a thin progress bar (`.mprog`) and the
 * side summary hides — same breakpoints as the design CSS.
 */

const RAIL: Array<{ step: EnrollPageStep; label: string; sub: string }> = [
  { step: 'plan', label: 'Choose plan', sub: 'Spark, Flame, Ember or Community' },
  { step: 'legal', label: 'Agreements', sub: 'Review and sign' },
  { step: 'billing', label: 'Billing', sub: 'Secured by Stripe' },
  { step: 'broker', label: 'Connect brokerage', sub: 'Tradier and more' },
  { step: 'agent', label: 'Configure agent', sub: 'Confirm your setup' },
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
  const railIndex = step ? RAIL.findIndex((r) => r.step === step) : -1
  const progressPct = railIndex >= 0 ? Math.round(((railIndex + 1) / RAIL.length) * 100) : 0

  return (
    <div className="if-enroll">
      <header className="top">
        <div className="top-in">
          <Link href="/" aria-label="IronForge home"><Wordmark markClass="h-6 w-auto" textClass="text-base" /></Link>
          {topRight === 'login' ? (
            <span className="secure">
              Already have an account? <Link href="/login" className="link" style={{ textDecoration: 'none', color: 'var(--accent)' }}>Log in</Link>
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
            {RAIL.map((r, i) => {
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
