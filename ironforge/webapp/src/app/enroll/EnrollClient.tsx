'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import CustomerShell from '@/components/customer/CustomerShell'
import { BOT_PLANS, COMMUNITY_PLAN, MARKETING_TIERS } from '@/lib/billing/plans'

/**
 * The enrollment funnel, driven entirely by the /api/v1 endpoints.
 *
 * The SERVER owns funnel position — every response carries `next_step`, and this
 * component renders whatever the server says rather than keeping its own idea of
 * progress. That is what makes the funnel resumable from a fresh device or an email
 * link (§3 DONE-01): reloading asks the server where you are instead of starting over.
 *
 * Errors come back in the shared envelope, so `message` is always safe to show a
 * customer — provider text never reaches here (§6, §11).
 */

type Step = 'plan' | 'legal' | 'billing' | 'brokerage' | 'account' | 'configure' | 'done'

interface LegalDoc {
  code: string
  title: string
  version: string
  contentUri: string
  accepted: boolean
}

interface BrokerAccount {
  id: string
  mask: string | null
  eligibility: string | null
  ineligible_reason: string | null
}

interface Conn {
  id: string
  provider: string
  status: string
  accounts: BrokerAccount[]
}

const STEP_ORDER: Step[] = ['plan', 'legal', 'billing', 'brokerage', 'account', 'configure']
const STEP_LABEL: Record<Step, string> = {
  plan: 'Plan',
  legal: 'Agreements',
  billing: 'Payment',
  brokerage: 'Brokerage',
  account: 'Account',
  configure: 'Configure',
  done: 'Done',
}

function Stepper({ current }: { current: Step }) {
  const idx = STEP_ORDER.indexOf(current)
  return (
    <ol className="mb-8 flex flex-wrap items-center gap-x-2 gap-y-2 text-[11px]">
      {STEP_ORDER.map((s, i) => {
        const done = idx > i
        const active = idx === i
        return (
          <li key={s} className="flex items-center gap-2">
            <span
              className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                done ? 'bg-emerald-600 text-black' : active ? 'bg-amber-500 text-black' : 'bg-white/10 text-gray-500'
              }`}
              aria-hidden
            >
              {done ? '✓' : i + 1}
            </span>
            <span className={active ? 'font-semibold text-white' : done ? 'text-gray-400' : 'text-gray-600'}>
              {STEP_LABEL[s]}
            </span>
            {i < STEP_ORDER.length - 1 ? <span className="text-gray-700">›</span> : null}
          </li>
        )
      })}
    </ol>
  )
}

export default function EnrollClient() {
  const [enrollmentId, setEnrollmentId] = useState<string | null>(null)
  const [step, setStep] = useState<Step>('plan')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [docs, setDocs] = useState<LegalDoc[]>([])
  const [outstanding, setOutstanding] = useState<string[]>([])
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [conns, setConns] = useState<Conn[]>([])

  /** Every call funnels through here so the error envelope is handled in ONE place. */
  const call = useCallback(async (url: string, init?: RequestInit) => {
    const res = await fetch(url, init)
    const body = await res.json().catch(() => null)
    if (!res.ok) {
      throw new Error(body?.message || 'Something went wrong. Please try again.')
    }
    return body
  }, [])

  // Create or RESUME on mount. The server decides the step; this never guesses.
  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const d = await call('/api/v1/enrollments', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ source: 'enroll_page' }),
        })
        if (!alive) return
        setEnrollmentId(d.enrollment.id)
        setStep((d.next_step as Step) ?? 'plan')
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'Could not start setup.')
      }
    })()
    return () => { alive = false }
  }, [call])

  const loadLegal = useCallback(async (id: string) => {
    const d = await call(`/api/v1/enrollments/${id}/legal`)
    setDocs(d.documents ?? [])
    setOutstanding(d.outstanding ?? [])
    // Pre-tick what is already accepted; a customer must not re-agree to something the
    // record already shows they agreed to.
    const next: Record<string, boolean> = {}
    for (const doc of d.documents ?? []) next[doc.code] = doc.accepted
    setChecked(next)
  }, [call])

  const loadAccounts = useCallback(async () => {
    const d = await call('/api/brokerage/connections')
    setConns(d.connections ?? [])
  }, [call])

  useEffect(() => {
    if (!enrollmentId) return
    if (step === 'legal') loadLegal(enrollmentId).catch((e) => setError(String(e.message)))
    if (step === 'account' || step === 'brokerage') loadAccounts().catch((e) => setError(String(e.message)))
  }, [enrollmentId, step, loadLegal, loadAccounts])

  async function choosePlan(plan: string) {
    if (!enrollmentId) return
    setBusy(true); setError(null)
    try {
      await call(`/api/v1/enrollments/${enrollmentId}/plan`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ plan }),
      })
      setStep('legal')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save your plan.')
    } finally { setBusy(false) }
  }

  async function acceptLegal() {
    if (!enrollmentId) return
    setBusy(true); setError(null)
    try {
      await call(`/api/v1/enrollments/${enrollmentId}/acceptances`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ accepted: Object.keys(checked).filter((c) => checked[c]) }),
      })
      setStep('billing')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not record your agreement.')
    } finally { setBusy(false) }
  }

  const allRequiredChecked = outstanding.every((c) => checked[c]) &&
    docs.filter((d) => !d.accepted).every((d) => checked[d.code])

  return (
    <CustomerShell membership={null}>
      <div className="mx-auto max-w-2xl">
        <h1 className="text-2xl font-bold text-white">Set up your strategy</h1>
        <p className="mt-1 text-sm text-gray-400">
          A few steps. You can leave and come back — we remember where you were.
        </p>

        <div className="mt-8">
          <Stepper current={step} />
        </div>

        {error ? (
          <p className="mb-4 rounded-lg border border-red-700/40 bg-red-950/30 px-4 py-3 text-sm text-red-300">
            {error}
          </p>
        ) : null}

        {!enrollmentId && !error ? (
          <div className="h-40 animate-pulse rounded-2xl border border-forge-border bg-forge-card/40" />
        ) : null}

        {/* ── Plan ─────────────────────────────────────────────────────────── */}
        {enrollmentId && step === 'plan' ? (
          <div className="space-y-3">
            {[
              { key: 'spark', name: BOT_PLANS.spark.productName, price: BOT_PLANS.spark.priceMonthly, blurb: BOT_PLANS.spark.blurb },
              { key: 'flame', name: BOT_PLANS.flame.productName, price: BOT_PLANS.flame.priceMonthly, blurb: BOT_PLANS.flame.blurb },
              { key: 'community', name: COMMUNITY_PLAN.name, price: COMMUNITY_PLAN.priceMonthly, blurb: 'Chat, briefings and education. No automated trading.' },
            ].map((p) => (
              <button
                key={p.key}
                type="button"
                disabled={busy}
                onClick={() => choosePlan(p.key)}
                className="flex w-full items-center gap-4 rounded-xl border border-forge-border bg-forge-card/60 p-5 text-left transition hover:border-amber-500/50 disabled:opacity-60"
              >
                <div className="min-w-0 flex-1">
                  <div className="text-base font-bold text-white">{p.name}</div>
                  <p className="mt-0.5 text-sm text-gray-400">{p.blurb}</p>
                </div>
                <div className="shrink-0 text-right">
                  <div className="text-lg font-bold text-white">${p.price}</div>
                  <div className="text-[11px] text-gray-500">/month</div>
                </div>
              </button>
            ))}
          </div>
        ) : null}

        {/* ── Legal ────────────────────────────────────────────────────────── */}
        {enrollmentId && step === 'legal' ? (
          <div className="rounded-2xl border border-forge-border bg-forge-card/60 p-6">
            <h2 className="text-base font-bold text-white">Agreements</h2>
            <p className="mt-1 text-sm text-gray-400">
              {/* Only the documents this plan requires are shown (§3) — a Community member
                  is never asked to sign a trading authorization they cannot use. */}
              These apply to the plan you chose.
            </p>
            <ul className="mt-4 space-y-3">
              {docs.map((d) => (
                <li key={d.code} className="flex items-start gap-3">
                  <input
                    id={`doc-${d.code}`}
                    type="checkbox"
                    checked={Boolean(checked[d.code])}
                    disabled={d.accepted}
                    onChange={(e) => setChecked((c) => ({ ...c, [d.code]: e.target.checked }))}
                    className="mt-1 h-4 w-4 shrink-0 accent-amber-500"
                  />
                  <label htmlFor={`doc-${d.code}`} className="min-w-0 text-sm text-gray-200">
                    I agree to the{' '}
                    <Link href={d.contentUri} className="font-semibold text-amber-500 hover:text-amber-400" target="_blank">
                      {d.title}
                    </Link>{' '}
                    <span className="text-gray-500">(v{d.version})</span>
                    {d.accepted ? <span className="ml-2 text-[11px] text-emerald-400">already accepted</span> : null}
                  </label>
                </li>
              ))}
            </ul>
            <button
              type="button"
              disabled={busy || !allRequiredChecked}
              onClick={acceptLegal}
              className="mt-6 rounded-lg bg-amber-500 px-5 py-2.5 text-sm font-semibold text-black transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? 'Saving…' : 'Agree and continue'}
            </button>
          </div>
        ) : null}

        {/* ── Billing ──────────────────────────────────────────────────────── */}
        {enrollmentId && step === 'billing' ? (
          <div className="rounded-2xl border border-forge-border bg-forge-card/60 p-6">
            <h2 className="text-base font-bold text-white">Payment</h2>
            <p className="mt-1 text-sm leading-relaxed text-gray-400">
              Checkout is handled by Stripe. Your {MARKETING_TIERS.starter.name} trial runs for five
              eligible trading days — days the market is open and your strategy can trade — so a
              weekend or a holiday never uses one up.
            </p>
            <button
              type="button"
              onClick={() => setStep('brokerage')}
              className="mt-5 rounded-lg bg-amber-500 px-5 py-2.5 text-sm font-semibold text-black transition hover:bg-amber-400"
            >
              Continue
            </button>
          </div>
        ) : null}

        {/* ── Brokerage + account selection ────────────────────────────────── */}
        {enrollmentId && (step === 'brokerage' || step === 'account') ? (
          <div className="rounded-2xl border border-forge-border bg-forge-card/60 p-6">
            <h2 className="text-base font-bold text-white">Choose the account to trade</h2>
            {conns.length === 0 ? (
              <>
                <p className="mt-1 text-sm text-gray-400">
                  Connect the brokerage you already use. Your funds stay in your own account.
                </p>
                <Link
                  href="/onboarding/brokerage"
                  className="mt-5 inline-flex rounded-lg bg-[#FD5301] px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-[#e04a00]"
                >
                  Connect a brokerage
                </Link>
              </>
            ) : (
              <ul className="mt-4 space-y-2">
                {conns.flatMap((c) =>
                  c.accounts.map((a, i) => {
                    const ok = a.eligibility === 'eligible'
                    return (
                      <li
                        key={`${c.id}-${i}`}
                        className="rounded-lg border border-white/10 bg-black/20 px-4 py-3"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-sm text-gray-200">{a.mask ?? '••••'}</span>
                          <span className="text-xs text-gray-500">{c.provider}</span>
                          <span
                            className={`ml-auto text-[10px] font-bold uppercase tracking-wider ${
                              ok ? 'text-emerald-400' : 'text-gray-500'
                            }`}
                          >
                            {ok ? 'Eligible' : 'Not eligible'}
                          </span>
                        </div>
                        {/* The REMEDIABLE reason, never a bare refusal. A customer who can
                            see the account in their broker needs to know what to fix. */}
                        {!ok && a.ineligible_reason ? (
                          <p className="mt-1 text-xs leading-snug text-gray-500">{a.ineligible_reason}</p>
                        ) : null}
                      </li>
                    )
                  }),
                )}
              </ul>
            )}
          </div>
        ) : null}

        {/* ── Configure / activate — deliberately not built yet ─────────────── */}
        {enrollmentId && (step === 'configure' || step === 'done') ? (
          <div className="rounded-2xl border border-forge-border bg-forge-card/60 p-6">
            <h2 className="text-base font-bold text-white">Almost there</h2>
            <p className="mt-1 text-sm leading-relaxed text-gray-400">
              Strategy configuration is the last step. We&apos;ll email you the moment it opens.
            </p>
          </div>
        ) : null}
      </div>
    </CustomerShell>
  )
}
