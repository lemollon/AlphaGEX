import { useEffect, useState } from 'react'
import { View, Text, Platform } from 'react-native'
import * as WebBrowser from 'expo-web-browser'
import { ApiError, api, API_BASE } from '@/api/client'
import type { MobileMe } from '@/api/types'
import { canPurchaseInApp } from '@/billing/store-policy'
import { productIdFor } from '@/billing/apple-products'
import { initIap, teardownIap, loadProducts, purchase as purchaseProduct, restorePurchases, type IapProduct } from '@/billing/apple-iap'
import { space, type, font } from '@/theme/tokens'
import { useTheme } from '@/theme/ThemeContext'
import { Button, Loading } from '@/components/ui'
import { EnrollShell } from '@/enroll/Shell'
import { useEnrollment } from '@/enroll/useEnrollment'
import { getLegal, acceptLegal, checkMembership, resumeEnrollment, getPlanCatalog } from '@/enroll/api'
import { routeForNextStep, PAGE_RANK } from '@/enroll/steps'
import type { PlanCatalog } from '@/enroll/types'

/**
 * Billing (UAT #6, screen 5 of 9).
 *
 * SPEC CHANGE 2026-09-05 (App Store Guideline 3.1.1 — the iOS build was IN REVIEW):
 * NO purchase surface opened in-app on ANY platform. The original brief's "Pay with
 * card" (hosted Stripe Checkout via an auth session) was REMOVED entirely — a real
 * in-app purchase path did not exist yet anywhere, so "Coming soon" was the only
 * honest state.
 *
 * 2026-09-18 (Apple IAP PR): iOS now has that path — StoreKit 2 via expo-iap
 * (src/billing/apple-iap.ts). `canPurchaseInApp('ios')` is true, so iOS shows the
 * REAL product for `enrollment.selected_plan` (name, what it includes, StoreKit's
 * own localized price), a Subscribe button, Restore Purchases, and the mandatory
 * Apple subscription disclosure block. Android/web are UNCHANGED — Play Billing is
 * out of scope for this PR, so those platforms still show the disabled "Coming
 * soon" button and can only continue via:
 *
 *   "I already subscribed on the web" — reads GET /api/billing/membership; if live,
 *   re-resumes the enrollment (the server re-derives billing_pending -> complete/
 *   setup_required from Stripe state directly, so this works regardless of which
 *   checkout flow the customer used on ironforge.trade) and continues forward.
 *   Otherwise shows an inline "No active subscription found" + Refresh — never a
 *   URL, never "go pay at ironforge.trade" copy; naming the destination would
 *   itself be the call-to-action Guideline 3.1.1 exists to prevent.
 *
 * The iOS StoreKit purchase reaches the exact same continuation: once the server
 * verifies the transaction (purchase-updated listener -> POST /api/billing/apple/
 * verify -> finishTransaction), this screen re-resumes the enrollment and follows
 * next_step forward — same call as "I already subscribed on the web" makes.
 *
 * Community's clickwrap (Terms/Privacy/Refund — no standalone legal screen) is
 * recorded here, same point in the funnel as the web billing submit, before any of
 * the actions below is offered.
 */
export default function BillingScreen() {
  const { colors: color } = useTheme()
  const { enrollment, busy, setBusy, error, setError, router } = useEnrollment('billing')
  const [catalog, setCatalog] = useState<PlanCatalog | null>(null)
  const [checked, setChecked] = useState(false)
  const [notFound, setNotFound] = useState(false)

  const [customerId, setCustomerId] = useState<string | null>(null)
  const [iapProducts, setIapProducts] = useState<IapProduct[]>([])
  const [iapReady, setIapReady] = useState(false)
  const [purchasingId, setPurchasingId] = useState<string | null>(null)
  const [restoring, setRestoring] = useState(false)
  const [legal, setLegal] = useState<{ terms: string; privacy: string } | null>(null)

  const isCommunity = enrollment?.selected_plan === 'community'
  const platform = Platform.OS === 'ios' ? 'ios' : Platform.OS === 'android' ? 'android' : 'web'
  const storeLabel = Platform.OS === 'ios' ? 'Subscribe with Apple' : 'Subscribe with Google Play'
  const iapEnabled = canPurchaseInApp(platform)

  useEffect(() => {
    getPlanCatalog()
      .then(setCatalog)
      .catch(() => {})
  }, [])

  /**
   * Terms/Privacy links for the Apple disclosure block — the SAME URIs the web
   * legal step and the web clickwrap point at (webapp/src/lib/enrollment/legal.ts:
   * TERMS -> '/terms', PRIVACY -> '/privacy'), never invented here. Both documents
   * are 'core' scope, so they are present in the legal block for every plan.
   */
  useEffect(() => {
    if (!enrollment) return
    getLegal(enrollment.id)
      .then((res) => {
        const terms = res.documents.find((d) => d.code === 'TERMS')?.contentUri ?? '/terms'
        const privacy = res.documents.find((d) => d.code === 'PRIVACY')?.contentUri ?? '/privacy'
        setLegal({ terms, privacy })
      })
      .catch(() => {})
  }, [enrollment])

  /**
   * iOS only: connect StoreKit, load the four products, and look up the signed-in
   * customer's id for `appAccountToken` (matches a transaction back to this account
   * server-side, see apple-iap.ts). `initIap` is idempotent — safe even if this
   * effect re-runs — and its listeners stay wired for the life of the app session.
   */
  useEffect(() => {
    if (!iapEnabled) return
    let alive = true

    api<MobileMe>('/api/auth/mobile/me')
      .then((me) => {
        if (alive) setCustomerId(me.customer?.id ?? null)
      })
      .catch(() => {})

    initIap({
      onError: (message) => {
        setPurchasingId(null)
        setError(message)
      },
      onVerified: onPurchaseVerified,
    })
      .then(() => loadProducts())
      .then((products) => {
        if (!alive) return
        setIapProducts(products)
        setIapReady(true)
      })
      .catch(() => {
        if (alive) setError('Could not load subscription options from the App Store.')
      })

    return () => {
      alive = false
      teardownIap().catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [iapEnabled])

  /** Community clickwrap — Terms/Privacy/Refund, recorded before either billing action. */
  async function acceptCommunityClickwrap(): Promise<void> {
    if (!enrollment || !isCommunity) return
    const legalBlock = await getLegal(enrollment.id)
    if (legalBlock.documents.every((d) => d.accepted)) return
    const d = await acceptLegal(
      enrollment.id,
      legalBlock.documents.map((doc) => doc.code),
    )
    if (!d.ok) throw new Error('Please accept the required agreements to continue.')
  }

  /**
   * The StoreKit purchase reached the same finish line "I already subscribed on the
   * web" does: re-resume so the server re-derives billing_pending's next transition
   * from the freshly-written subscription row, then follow next_step forward.
   * Deliberately does NOT read the `enrollment` closure captured when `initIap` was
   * first called — `resumeEnrollment()` needs no id, so this stays correct even if
   * a purchase finishes long after the screen's initial enrollment fetch.
   */
  async function onPurchaseVerified(): Promise<void> {
    setPurchasingId(null)
    try {
      const d = await resumeEnrollment()
      const canonical = routeForNextStep(d.next_step, d.enrollment.selected_plan)
      if (canonical.rank > PAGE_RANK.billing) {
        router.push(canonical.route as never)
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.humanMessage : (e as Error).message)
    }
  }

  async function onSubscribe(productId: string) {
    if (!customerId || purchasingId || busy) return
    setError(null)
    if (isCommunity) {
      try {
        await acceptCommunityClickwrap()
      } catch (e) {
        setError((e as Error).message)
        return
      }
    }
    setPurchasingId(productId)
    try {
      // The result arrives asynchronously through the purchase-updated listener
      // (onVerified/onError passed to initIap above), never through this call.
      await purchaseProduct(productId, customerId)
    } catch (e) {
      setPurchasingId(null)
      setError(e instanceof Error ? e.message : 'Could not start the purchase.')
    }
  }

  async function onRestore() {
    setRestoring(true)
    setError(null)
    try {
      const result = await restorePurchases()
      if (result.verified > 0) {
        await onPurchaseVerified()
      } else {
        setError('No purchases found to restore for this Apple ID.')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not restore purchases.')
    } finally {
      setRestoring(false)
    }
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

  async function openLegal(path: string) {
    await WebBrowser.openBrowserAsync(`${API_BASE}${path}`)
  }

  const price = isCommunity
    ? catalog?.community.price_monthly
    : catalog?.bots.find((b) => enrollment?.selected_plan === b.slug)?.price_monthly ??
      (enrollment?.selected_plan === 'both' ? catalog?.both.price_monthly : undefined)

  // The Apple product ID for the plan already chosen earlier in the funnel — this
  // screen sells exactly ONE product, the plan the customer picked, same as the web
  // billing step; it is never a general storefront listing all four.
  const iapLookupKey = enrollment?.selected_plan ? `${enrollment.selected_plan}_monthly` : null
  const iapProductId = iapLookupKey ? productIdFor(iapLookupKey) : null
  const iapProduct = iapProductId ? iapProducts.find((p) => p.productId === iapProductId) : undefined
  const planInfo = planLabel(enrollment?.selected_plan ?? null, catalog)

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

          {iapEnabled ? (
            <View style={{ marginBottom: space.md }}>
              {!iapProductId ? (
                <Text style={[type.body, { color: color.neg, marginBottom: space.md }]}>
                  Subscription option unavailable for this plan. Please contact support.
                </Text>
              ) : !iapReady ? (
                <Loading label="Loading subscription options…" />
              ) : (
                <>
                  {planInfo ? (
                    <View style={{ marginBottom: space.md }}>
                      <Text style={[type.body, { color: color.text, fontFamily: font.bodyBold, fontSize: 17 }]}>
                        {planInfo.name}
                      </Text>
                      <Text style={[type.label, { color: color.textDim, marginTop: 2 }]}>{planInfo.blurb}</Text>
                    </View>
                  ) : null}
                  <Button
                    label={
                      iapProduct
                        ? `Subscribe · ${iapProduct.displayPrice}/month`
                        : 'Subscribe with Apple'
                    }
                    onPress={() => onSubscribe(iapProductId)}
                    busy={purchasingId === iapProductId}
                    disabled={!customerId || !iapProduct || (purchasingId != null && purchasingId !== iapProductId)}
                  />
                  {/*
                    Mandatory Apple subscription disclosure (App Review Guideline
                    3.1.2): title, duration, price, auto-renewal terms, and the
                    Terms of Use / Privacy Policy the customer is agreeing to.
                  */}
                  <Text style={[type.label, { color: color.muted, marginTop: space.md, lineHeight: 18 }]}>
                    {planInfo?.name ?? 'IronForge Membership'} · 1 month
                    {iapProduct ? ` · ${iapProduct.displayPrice}/month` : ''}. Payment will be charged to
                    your Apple ID account. This subscription automatically renews unless auto-renew is
                    turned off at least 24 hours before the end of the current period. Manage or cancel
                    any time in your App Store account settings.
                    {legal ? (
                      <>
                        {' '}
                        <Text style={{ color: color.accent }} onPress={() => openLegal(legal.terms)}>
                          Terms of Use
                        </Text>
                        {' and '}
                        <Text style={{ color: color.accent }} onPress={() => openLegal(legal.privacy)}>
                          Privacy Policy
                        </Text>
                        {' apply.'}
                      </>
                    ) : null}
                  </Text>
                </>
              )}
              <View style={{ marginTop: space.md }}>
                <Button label="Restore Purchases" onPress={onRestore} busy={restoring} variant="secondary" />
              </View>
            </View>
          ) : (
            <View style={{ gap: space.sm, marginBottom: space.md }}>
              <Button label={`${storeLabel} · Coming soon`} onPress={() => {}} disabled />
            </View>
          )}
          {!iapEnabled ? (
            <Text style={[type.label, { color: color.muted, marginBottom: space.lg }]}>
              In-app purchase is not available yet on this build.
            </Text>
          ) : null}

          <View style={{ marginTop: space.lg }}>
            <Button
              label="I already subscribed on the web"
              onPress={checkWebSubscription}
              busy={busy}
              variant="secondary"
            />
          </View>

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

/** Plan name + one-line description for the disclosure block and the product row —
 *  reads from the SAME catalogue the "Due after setup" price above uses, never a
 *  hardcoded second copy of plan names that could drift from it. */
function planLabel(plan: string | null, catalog: PlanCatalog | null): { name: string; blurb: string } | null {
  if (!plan || !catalog) return null
  if (plan === 'community') {
    return { name: catalog.community.name, blurb: 'Forge Community chat and education access.' }
  }
  if (plan === 'both') {
    return { name: 'Spark + Flame', blurb: 'Both trading agents in one subscription.' }
  }
  const bot = catalog.bots.find((b) => b.slug === plan)
  return bot ? { name: bot.name, blurb: bot.blurb } : null
}
