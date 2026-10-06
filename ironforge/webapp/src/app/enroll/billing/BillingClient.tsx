'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import EnrollShell from '../EnrollShell'
import { useEnrollment } from '../useEnrollment'
import { PAGE_RANK, routeForNextStep } from '../steps'
import StripeCardForm from './StripeCardForm'
import { MARKETING_TIERS, TRIAL_DAYS } from '@/lib/billing/plans'
import { track } from '@/lib/analytics/track'
import { trackEnrollStepComplete } from '@/lib/analytics/enroll'

/**
 * BILL-COMM-01 / BILL-AUTO-01 — Billing (10/5 reorder: step 5, right after Connect
 * brokerage; Community made free 2026-10-05).
 *
 * Automate (Spark/Flame; Ember never reaches this screen — see plan/PlanClient.tsx
 * and broker/BrokerClient.tsx): an EMBEDDED Stripe Elements Payment Element,
 * server-created via a SetupIntent (POST /api/billing/setup-intent) — $0 due today,
 * the trial begins only at activation, never here (unchanged from before this
 * reorder; see lib/billing/stripe.ts createSetupIntent). Falls back to the previous
 * hosted-Checkout redirect (saveAutomateCard) when
 * NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY is not configured on this deployment, so a
 * missing env var degrades gracefully instead of breaking enrollment.
 *
 * Community branch is effectively a RESUME FALLBACK now — PlanClient finalizes the
 * free join immediately after the "Choose agent" screen, so a normal flow never
 * visits this screen for Community. An enrollment migrated from before this reorder
 * (or any resumed Community row that never got the fast-forward) still lands here and
 * still works: it records the Terms/Privacy/Refund clickwrap, then
 * POST /api/billing/checkout writes the free entitlement and hands back an internal
 * url, not a Stripe redirect.
 *
 * Returning from Stripe (?checkout=success, hosted-Checkout fallback only) re-resumes;
 * the server re-derives billing completion from Stripe state directly, so this works
 * even before the webhook lands.
 */

interface LegalDoc {
  code: string
  title: string
  contentUri: string
}

const STRIPE_PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY

export default function BillingClient() {
  const { enrollment, busy, setBusy, error, setError, call, resume, router } = useEnrollment('billing')
  const params = useSearchParams()
  const checkout = params.get('checkout')
  const [finalizing, setFinalizing] = useState(checkout === 'success')
  const [clientSecret, setClientSecret] = useState<string | null>(null)
  const [loadingSecret, setLoadingSecret] = useState(false)

  const isCommunity = enrollment?.selected_plan === 'community'
  const canEmbed = Boolean(STRIPE_PUBLISHABLE_KEY)

  // Back from Stripe (hosted-Checkout fallback): follow the server's position FORWARD.
  // The resume endpoint checks Stripe directly (webhook-lag immune), so success
  // normally advances immediately.
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

  // Fetch the SetupIntent client_secret as soon as it's clear this is the embedded
  // Automate path — never for Community, never when the fallback env var is unset.
  useEffect(() => {
    if (!enrollment || isCommunity || !canEmbed || finalizing || clientSecret) return
    setLoadingSecret(true)
    call('/api/billing/setup-intent', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ enrollment_id: enrollment.id }),
    })
      .then((d) => setClientSecret(d.client_secret))
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not start billing setup.'))
      .finally(() => setLoadingSecret(false))
  }, [enrollment, isCommunity, canEmbed, finalizing, clientSecret, call, setError])

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

  /** Fallback only — used when NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY is not configured. */
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

  /** The embedded form's card was saved — re-resume so the server (which re-derives
   *  billing completion from Stripe directly) advances us to Review. */
  async function onCardSaved() {
    setBusy(true)
    setError(null)
    try {
      const r = await resume()
      if (!r) return
      track('billing_trial_started', { agent: r.enrollment.selected_plan ?? undefined })
      trackEnrollStepComplete('billing')
      const canonical = routeForNextStep(r.next_step, r.enrollment.selected_plan)
      router.push(canonical.route)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Your card was saved, but we could not continue automatically. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  const headline = isCommunity ? 'One final step.' : 'Prepare to automate.'
  const subline = isCommunity
    ? 'Accept the agreements below to activate your free Forge Community membership.'
    : 'Add a payment method to finish setting up your trading agent.'
  const backHref = isCommunity ? '/enroll/plan' : '/enroll/broker'

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
          ) : canEmbed ? (
            <div className="card pad" style={{ marginTop: 20 }}>
              <h3>Payment method</h3>
              {loadingSecret && !clientSecret ? <div style={{ height: 120 }} /> : null}
              {clientSecret && STRIPE_PUBLISHABLE_KEY ? (
                <StripeCardForm publishableKey={STRIPE_PUBLISHABLE_KEY} clientSecret={clientSecret} onSaved={onCardSaved} />
              ) : null}
              <p className="help" style={{ marginTop: 12 }}>
                Your trial begins only after you activate trading on the next screen.
              </p>
            </div>
          ) : (
            <>
              <button type="button" disabled={busy} onClick={saveAutomateCard} className="btn btn-accent btn-block btn-lg" style={{ marginTop: 20 }}>
                {busy ? 'Starting checkout…' : 'Save Payment & Continue'}
              </button>
              <p className="help" style={{ marginTop: 12 }}>
                Your trial begins only after you activate trading on the next screen.
              </p>
            </>
          )}

          <div className="nav-row">
            <Link href={backHref} className="btn">← Back</Link>
          </div>
        </>
      ) : null}
    </EnrollShell>
  )
}
