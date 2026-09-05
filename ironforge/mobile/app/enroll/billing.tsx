import { useEffect, useState } from 'react'
import { View, Text, Platform } from 'react-native'
import { ApiError } from '@/api/client'
import { canPurchaseInApp } from '@/billing/store-policy'
import { color, space, type, font } from '@/theme/tokens'
import { Button, Loading } from '@/components/ui'
import { EnrollShell } from '@/enroll/Shell'
import { useEnrollment } from '@/enroll/useEnrollment'
import { getLegal, acceptLegal, checkMembership, resumeEnrollment, getPlanCatalog } from '@/enroll/api'
import { routeForNextStep, PAGE_RANK } from '@/enroll/steps'
import type { PlanCatalog } from '@/enroll/types'

/**
 * Billing (UAT #6, screen 5 of 9).
 *
 * SPEC CHANGE 2026-09-05 (App Store Guideline 3.1.1 — the iOS build is IN REVIEW):
 * NO purchase surface opens in-app on ANY platform. The original brief's "Pay with
 * card" (hosted Stripe Checkout via an auth session) is REMOVED entirely, not just
 * hidden on iOS — canPurchaseInApp() in src/billing/store-policy.ts is hardcoded false
 * everywhere until PR B (react-native-iap) ships. This screen offers only:
 *
 *   1. "Subscribe with Apple / Google Play" — primary, always disabled, "Coming soon".
 *   2. "I already subscribed on the web" — reads GET /api/billing/membership; if live,
 *      re-resumes the enrollment (the server re-derives billing_pending -> complete/
 *      setup_required from Stripe state directly, so this works regardless of which
 *      checkout flow the customer used on ironforge.trade) and continues forward.
 *      Otherwise shows an inline "No active subscription found" + Refresh — never a
 *      URL, never "go pay at ironforge.trade" copy; naming the destination would
 *      itself be the call-to-action Guideline 3.1.1 exists to prevent.
 *
 * Community's clickwrap (Terms/Privacy/Refund — no standalone legal screen) is
 * recorded here, same point in the funnel as the web billing submit, before either
 * action below is offered.
 */
export default function BillingScreen() {
  const { enrollment, busy, setBusy, error, setError, router } = useEnrollment('billing')
  const [catalog, setCatalog] = useState<PlanCatalog | null>(null)
  const [checked, setChecked] = useState(false)
  const [notFound, setNotFound] = useState(false)

  const isCommunity = enrollment?.selected_plan === 'community'
  const platform = Platform.OS === 'ios' ? 'ios' : Platform.OS === 'android' ? 'android' : 'web'
  const storeLabel = Platform.OS === 'ios' ? 'Subscribe with Apple' : 'Subscribe with Google Play'

  useEffect(() => {
    getPlanCatalog()
      .then(setCatalog)
      .catch(() => {})
  }, [])

  /** Community clickwrap — Terms/Privacy/Refund, recorded before either billing action. */
  async function acceptCommunityClickwrap(): Promise<void> {
    if (!enrollment || !isCommunity) return
    const legal = await getLegal(enrollment.id)
    if (legal.documents.every((d) => d.accepted)) return
    const d = await acceptLegal(
      enrollment.id,
      legal.documents.map((doc) => doc.code),
    )
    if (!d.ok) throw new Error('Please accept the required agreements to continue.')
  }

  async function checkWebSubscription() {
    if (!enrollment || busy) return
    setBusy(true)
    setError(null)
    setNotFound(false)
    try {
      await acceptCommunityClickwrap()
      const membership = await checkMembership()
      setChecked(true)
      if (!membership.membership) {
        setNotFound(true)
        return
      }
      // Live entitlement exists — re-resume so the server re-derives billing_pending's
      // next transition (advanceBillingIfComplete) from Stripe state directly, then
      // follow next_step forward exactly like the web funnel does on checkout return.
      const d = await resumeEnrollment()
      const canonical = routeForNextStep(d.next_step, d.enrollment.selected_plan)
      if (canonical.rank > PAGE_RANK.billing) {
        router.push(canonical.route as never)
      } else {
        setNotFound(true)
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.humanMessage : (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const price = isCommunity
    ? catalog?.community.price_monthly
    : catalog?.bots.find((b) => enrollment?.selected_plan === b.slug)?.price_monthly ??
      (enrollment?.selected_plan === 'both' ? catalog?.both.price_monthly : undefined)

  return (
    <EnrollShell title="Billing" step={5} error={error}>
      {!enrollment ? (
        <Loading label="Loading…" />
      ) : (
        <>
          <Text style={[type.body, { color: color.textDim, marginBottom: space.lg }]}>
            {isCommunity
              ? 'Your Forge Community membership begins as soon as billing is set up.'
              : 'Your trial begins only after brokerage, agent, and activation are complete — never at billing.'}
          </Text>

          {price != null ? (
            <View style={{ marginBottom: space.xl }}>
              <Text style={[type.label, { color: color.muted }]}>Due after setup</Text>
              <Text style={[type.title, { color: color.text, fontFamily: font.display }]}>${price}/month</Text>
            </View>
          ) : null}

          <View style={{ gap: space.sm, marginBottom: space.md }}>
            <Button label={`${storeLabel} · Coming soon`} onPress={() => {}} disabled />
          </View>
          {/* TODO(PR B): wire react-native-iap here once it lands; canPurchaseInApp()
              flips true for the platforms it supports and this button becomes real. */}
          {!canPurchaseInApp(platform) ? (
            <Text style={[type.label, { color: color.muted, marginBottom: space.lg }]}>
              In-app purchase is not available yet on this build.
            </Text>
          ) : null}

          <Button label="I already subscribed on the web" onPress={checkWebSubscription} busy={busy} variant="secondary" />

          {checked && notFound ? (
            <Text style={[type.body, { color: color.neg, marginTop: space.md, textAlign: 'center' }]}>
              No active subscription found for this account.
            </Text>
          ) : null}
        </>
      )}
    </EnrollShell>
  )
}
