'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import EnrollShell from '../EnrollShell'
import { useEnrollment } from '../useEnrollment'
import { PAGE_RANK, routeForNextStep } from '../steps'
import { MARKETING_TIERS, TRIAL_DAYS } from '@/lib/billing/plans'

/**
 * BILL-COMM-01 / BILL-AUTO-01 — billing (July 29 handoff; Community made free 2026-10-05).
 *
 * Payment fields are HOSTED BY STRIPE (accepted deviation from the embedded-field
 * mockups) for Automate ONLY: Automate saves a card at $0 due (setup mode via the
 * server-validated `enrollment_setup` intent — the trial begins only at activation,
 * never here). Community is FREE — no card, no Stripe, ever (Leron, binding): this
 * screen records the clickwrap, then POST /api/billing/checkout writes the free
 * entitlement directly and hands back an internal url, not a Stripe redirect.
 *
 * Community has no standalone legal screen: its Terms / Privacy / Refund acceptance
 * is recorded as a clickwrap at THIS submit, before the free-join call.
 *
 * Returning from Stripe (?checkout=success, Automate only) re-resumes; the server
 * re-derives billing completion from Stripe state directly, so this works even before
 * the webhook lands.
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
      // Clickwrap: record the core acceptances (Terms / Privacy / Refund) BEFORE
      // joining — the doc requires binding acceptance at submit. Community is free, so
      // this call writes the entitlement directly and returns an internal url; there is
      // no card and no Stripe redirect.
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
      setError(e instanceof Error ? e.message : 'Could not join Community.')
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
    ? 'Accept the agreements below to activate your free Forge Community membership.'
    : 'Add a payment method, then complete your trading setup.'

  return (
    <EnrollShell headline={headline} subline={subline} maxWidthClass="max-w-3xl" step="billing" enrollment={enrollment}>
      {checkout === 'canceled' ? (
        <p className="help" style={{ marginBottom: 14 }}>Checkout was canceled — your card was not charged. Pick up where you left off below.</p>
      ) : null}
      {error ? <p className="err" style={{ marginBottom: 14 }}>{error}</p> : null}

      {!enrollment && !error ? <div className="card pad" style={{ height: 220 }} /> : null}

      {enrollment && finalizing ? (
        <div className="card pad">
          Confirming your payment method with Stripe…{' '}
          <button type="button" onClick={() => resume()} className="link">Check again</button>
        </div>
      ) : null}

      {enrollment && !finalizing ? (
        <>
          {/* Order summary */}
          <div className="card pad">
            <h3>Order summary</h3>
            {isCommunity ? (
              <div className="today" style={{ marginTop: 14 }}>
                <div><span>Forge Community</span><span><b>Free</b></span></div>
                <div><span className="help">No card · No Stripe subscription · Cancel anytime</span><span /></div>
                <div><span>Due today</span><span>$0.00</span></div>
              </div>
            ) : (
              <div className="today" style={{ marginTop: 14 }}>
                <div><span>Forge Automate</span><span>${MARKETING_TIERS.starter.priceMonthly.toFixed(2)}/month</span></div>
                <div><span className="help">{TRIAL_DAYS} trading-day free trial · Begins at activation</span><span /></div>
                <div><span>Due today</span><span>$0.00</span></div>
              </div>
            )}
            {isCommunity ? (
              <span className="badge ok" style={{ marginTop: 12, display: 'inline-block' }}>Free · No card required</span>
            ) : (
              <span className="badge ok" style={{ marginTop: 12, display: 'inline-block' }}>Card required · No charge today</span>
            )}
            {!isCommunity ? (
              <p className="powered" style={{ marginTop: 14 }}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                  <rect x="5" y="10.5" width="14" height="9" rx="2" />
                  <path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" />
                </svg>
                Payments are securely processed by Stripe.
              </p>
            ) : null}
          </div>

          {isCommunity ? (
            <>
              <button type="button" disabled={busy} onClick={payCommunity} className="btn btn-accent btn-block btn-lg" style={{ marginTop: 20 }}>
                {busy ? 'Joining…' : 'Join Community — Free'}
              </button>
              <p className="help" style={{ marginTop: 12, lineHeight: 1.5 }}>
                By continuing, you accept the{' '}
                <Link href="/terms" target="_blank" className="link">Terms of Service</Link>,{' '}
                <Link href="/privacy" target="_blank" className="link">Privacy Policy</Link>, and{' '}
                <Link href="/legal/refund-policy" target="_blank" className="link">Refund Policy</Link>.
              </p>
            </>
          ) : (
            <>
              <button type="button" disabled={busy} onClick={saveAutomateCard} className="btn btn-accent btn-block btn-lg" style={{ marginTop: 20 }}>
                {busy ? 'Starting checkout…' : 'Save Payment & Continue'}
              </button>
              <p className="help" style={{ marginTop: 12 }}>
                Your trial begins only after you connect a brokerage, configure an agent, and activate trading.
              </p>
            </>
          )}

          <div className="nav-row">
            <Link href="/enroll/plan" className="btn">← Back</Link>
          </div>
        </>
      ) : null}
    </EnrollShell>
  )
}
