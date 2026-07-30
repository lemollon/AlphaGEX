'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import EnrollShell from '../EnrollShell'
import { useEnrollment } from '../useEnrollment'
import { PAGE_RANK, routeForNextStep } from '../steps'
import { MARKETING_TIERS, TRIAL_DAYS } from '@/lib/billing/plans'

/**
 * BILL-COMM-01 / BILL-AUTO-01 — billing (July 29 handoff).
 *
 * Payment fields are HOSTED BY STRIPE (accepted deviation from the embedded-field
 * mockups): this screen is the order summary + the binding acceptance language, and
 * the CTA redirects to Stripe Checkout. Community pays $10 today (subscription mode);
 * Automate saves a card at $0 due (setup mode via the server-validated
 * `enrollment_setup` intent — the trial begins only at activation, never here).
 *
 * Community has no standalone legal screen: its Terms / Privacy / Refund acceptance
 * is recorded as a clickwrap at THIS submit, before the Stripe redirect.
 *
 * Returning from Stripe (?checkout=success) re-resumes; the server re-derives billing
 * completion from Stripe state directly, so this works even before the webhook lands.
 */

interface LegalDoc {
  code: string
  title: string
  contentUri: string
}

export default function BillingClient() {
  const { enrollment, busy, setBusy, error, setError, call, resume, router } = useEnrollment('billing')
  const params = useSearchParams()
  const checkout = params.get('checkout')
  const [finalizing, setFinalizing] = useState(checkout === 'success')

  const isCommunity = enrollment?.selected_plan === 'community'

  // Back from Stripe: follow the server's position FORWARD. The resume endpoint checks
  // Stripe directly (webhook-lag immune), so success normally advances immediately.
  useEffect(() => {
    if (checkout !== 'success' || !enrollment) return
    ;(async () => {
      const r = await resume()
      if (!r) return
      const canonical = routeForNextStep(r.next_step, r.enrollment.selected_plan)
      if (canonical.rank > PAGE_RANK.billing) {
        router.replace(canonical.route)
      } else {
        setFinalizing(false)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkout, enrollment?.id])

  async function payCommunity() {
    if (!enrollment) return
    setBusy(true)
    setError(null)
    try {
      // Clickwrap: record the core acceptances (Terms / Privacy / Refund) BEFORE the
      // Stripe redirect — the doc requires binding acceptance at submit, and the
      // acceptance moving the enrollment to billing_pending is what checkout expects.
      const legal = await call(`/api/v1/enrollments/${enrollment.id}/legal`)
      const codes = (legal.documents as LegalDoc[]).map((d) => d.code)
      await call(`/api/v1/enrollments/${enrollment.id}/acceptances`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ accepted: codes }),
      })
      const d = await call('/api/billing/checkout', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ bot: 'community', return_to: 'enroll' }),
      })
      window.location.assign(d.url)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start checkout.')
      setBusy(false)
    }
  }

  async function saveAutomateCard() {
    if (!enrollment) return
    setBusy(true)
    setError(null)
    try {
      const d = await call('/api/billing/checkout', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ intent: 'enrollment_setup', enrollment_id: enrollment.id }),
      })
      window.location.assign(d.url)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start checkout.')
      setBusy(false)
    }
  }

  const headline = isCommunity ? 'One final step.' : 'Prepare to automate.'
  const subline = isCommunity
    ? 'Set up billing to activate your Forge Community membership.'
    : 'Add a payment method, then complete your trading setup.'

  return (
    <EnrollShell headline={headline} subline={subline} maxWidthClass="max-w-3xl">
      <div className="rounded-2xl border border-forge-border bg-forge-card/60 p-6 lg:p-8">
        <h2 className="text-2xl font-bold text-white">Set up billing</h2>
        <p className="mt-1 text-sm text-gray-400">
          {isCommunity
            ? 'Your Forge Community membership begins today.'
            : 'Your card will not be charged until your free trial is complete.'}
        </p>

        {checkout === 'canceled' ? (
          <p className="mt-4 rounded-md border border-white/15 bg-black/30 px-3 py-2 text-sm text-gray-300">
            Checkout was canceled — your card was not charged. Pick up where you left off below.
          </p>
        ) : null}
        {error ? (
          <p className="mt-4 rounded-md border border-red-700/40 bg-red-950/30 px-3 py-2 text-sm text-red-300">{error}</p>
        ) : null}

        {!enrollment && !error ? (
          <div className="mt-6 h-56 animate-pulse rounded-2xl border border-forge-border bg-forge-card/40" />
        ) : null}

        {enrollment && finalizing ? (
          <div className="mt-6 rounded-xl border border-forge-border bg-black/20 p-6 text-sm text-gray-300">
            Confirming your payment method with Stripe…{' '}
            <button type="button" onClick={() => resume()} className="font-semibold text-amber-500 hover:text-amber-400">
              Check again
            </button>
          </div>
        ) : null}

        {enrollment && !finalizing ? (
          <>
            {/* Order summary */}
            <div className="mt-6 rounded-xl border border-forge-border bg-black/20 p-5">
              <h3 className="text-sm font-bold uppercase tracking-wider text-gray-400">Order summary</h3>
              {isCommunity ? (
                <>
                  <div className="mt-3 flex items-baseline justify-between">
                    <span className="text-sm text-gray-200">Forge Community</span>
                    <span className="text-sm font-semibold text-white">
                      ${MARKETING_TIERS.community.priceMonthly.toFixed(2)}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-gray-500">Monthly membership · Renews monthly</p>
                  <div className="mt-4 flex items-baseline justify-between border-t border-forge-border pt-4">
                    <span className="text-sm font-semibold text-gray-200">Due today</span>
                    <span className="text-2xl font-bold text-white">
                      ${MARKETING_TIERS.community.priceMonthly.toFixed(2)}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-gray-500">Cancel anytime.</p>
                </>
              ) : (
                <>
                  <div className="mt-3 flex items-baseline justify-between">
                    <span className="text-sm text-gray-200">Forge Automate</span>
                    <span className="text-sm font-semibold text-white">
                      ${MARKETING_TIERS.starter.priceMonthly.toFixed(2)} / month
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-gray-500">
                    {TRIAL_DAYS} trading-day free trial · Begins at activation
                  </p>
                  <div className="mt-4 flex items-baseline justify-between border-t border-forge-border pt-4">
                    <span className="text-sm font-semibold text-gray-200">Due today</span>
                    <span className="text-2xl font-bold text-white">$0.00</span>
                  </div>
                  <p className="mt-1 text-xs text-gray-500">
                    Then ${MARKETING_TIERS.starter.priceMonthly}/month after your trial.
                  </p>
                  <span className="mt-3 inline-block rounded-md border border-emerald-500/50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-emerald-400">
                    Card required · No charge today
                  </span>
                </>
              )}
              <p className="mt-4 flex items-center gap-1.5 text-xs text-gray-500">
                <span aria-hidden>🔒</span> Payments are securely processed by Stripe.
              </p>
            </div>

            {isCommunity ? (
              <>
                <button
                  type="button"
                  disabled={busy}
                  onClick={payCommunity}
                  className="mt-6 w-full rounded-lg bg-amber-500 px-5 py-3 text-sm font-semibold text-black transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busy ? 'Starting checkout…' : `Pay $${MARKETING_TIERS.community.priceMonthly} & Join Community`}
                </button>
                <p className="mt-3 text-xs leading-relaxed text-gray-500">
                  By continuing, you agree to recurring monthly billing until canceled and accept the{' '}
                  <Link href="/terms" target="_blank" className="text-amber-500 hover:underline">Terms of Service</Link>,{' '}
                  <Link href="/privacy" target="_blank" className="text-amber-500 hover:underline">Privacy Policy</Link>, and{' '}
                  <Link href="/legal/refund-policy" target="_blank" className="text-amber-500 hover:underline">Refund Policy</Link>.
                </p>
              </>
            ) : (
              <>
                <button
                  type="button"
                  disabled={busy}
                  onClick={saveAutomateCard}
                  className="mt-6 w-full rounded-lg bg-emerald-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busy ? 'Starting checkout…' : 'Save Payment & Continue'}
                </button>
                <p className="mt-3 text-xs text-gray-500">
                  Your trial begins only after you connect a brokerage, configure an agent, and activate trading.
                </p>
              </>
            )}

            <Link href="/enroll/plan" className="mt-5 inline-block text-sm text-gray-400 hover:text-white">
              ← Back to membership selection
            </Link>
          </>
        ) : null}
      </div>
    </EnrollShell>
  )
}
