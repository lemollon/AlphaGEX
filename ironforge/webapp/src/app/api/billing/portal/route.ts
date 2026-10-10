import { NextRequest, NextResponse } from 'next/server'
import { publicOrigin } from '@/lib/public-origin'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { billingReturn, type BillingClient } from '@/lib/mobile/deep-link'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'
import { isStripeConfigured, createBillingPortalSession } from '@/lib/billing/stripe'
import { resolvePortalConfiguration } from '@/lib/billing/portal-policy'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Opens the Stripe Customer Portal for the signed-in customer and returns its hosted
 * url. Customer-session guarded. Returns 409 with reason 'no_subscription' when the
 * user has never checked out (no Stripe customer yet) so the UI can point them at
 * plans instead; 503 until Stripe + the portal are provisioned, so the Billing page
 * degrades cleanly.
 *
 * 🚨 MOBILE GETS A DIFFERENT PORTAL, AND THAT IS THE WHOLE POINT.
 *
 * APP-039 ("Manage membership", Must Have, MVP) requires the app to open the supported
 * membership-management experience. App Review Guideline 3.1.1 bars an iOS app from
 * routing customers to a purchasing mechanism. Both hold at once only if the portal
 * mobile receives cannot sell anything: Stripe's DEFAULT configuration permits
 * CHANGING PLAN, which would put the $15 / $50 / $75 tiers one tap inside the app.
 *
 * So mobile is served STRIPE_PORTAL_CONFIG_MOBILE — a configuration with subscription
 * updates switched off and cancel / payment method / invoices left on. Web is unchanged
 * and keeps the full portal.
 *
 * 🚨 It FAILS CLOSED. If that configuration id is missing, mobile gets a 503 rather
 * than the default portal. The tempting fallback — "no config, just use the default" —
 * is precisely the 3.1.1 violation, and it would appear silently the first time someone
 * rotated an env var. An unavailable button is a bug; a plan-change surface inside the
 * iOS app is a rejected build.
 */
export async function POST(req: NextRequest) {
  // Cookie OR mobile bearer, so "Manage Membership & Billing" works from the app.
  const identity = await getCustomerIdentity()
  if (!identity) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  const session = { customerId: identity.customerId }
  // Derived from how the caller authenticated, never from the request body — a spoofed
  // flag would strand a web customer on a bridge page their browser cannot act on.
  const client: BillingClient = identity.source === 'bearer' ? 'mobile' : 'web'

  if (!isStripeConfigured() || !isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'Billing management isn’t available just yet — please try again shortly.' },
      { status: 503 },
    )
  }

  try {
    const rows = await customerQuery<{ stripe_customer_id: string | null }>(
      `SELECT stripe_customer_id FROM users WHERE id = $1 LIMIT 1`,
      [session.customerId],
    )
    const stripeCustomerId = rows[0]?.stripe_customer_id
    if (!stripeCustomerId) {
      return NextResponse.json(
        { ok: false, error: 'no_subscription', reason: 'no_subscription' },
        { status: 409 },
      )
    }

    // See the fail-closed note above. The rule itself lives in portal-policy.ts so it
    // has one definition and is covered by tests.
    const decision = resolvePortalConfiguration(client, process.env.STRIPE_PORTAL_CONFIG_MOBILE)
    if (!decision.allowed) {
      console.error(
        '[billing/portal] STRIPE_PORTAL_CONFIG_MOBILE is not set; refusing to open the ' +
          'default (plan-changing) portal for a mobile client.',
      )
      return NextResponse.json(
        {
          ok: false,
          error: decision.reason,
          message:
            'Membership management is temporarily unavailable. Please try again shortly.',
        },
        { status: 503 },
      )
    }

    const { url } = await createBillingPortalSession({
      customerId: stripeCustomerId,
      returnUrl: billingReturn(publicOrigin(req), client, '/account/billing'),
      ...(decision.configuration ? { configuration: decision.configuration } : {}),
    })
    return NextResponse.json({ ok: true, url })
  } catch (e) {
    console.error('[billing/portal] failed:', e)
    // Most common cause: the Customer Portal hasn't been enabled in the Stripe
    // dashboard yet. Surface a soft "try again", not a hard 500.
    return NextResponse.json(
      { ok: false, error: 'Billing management isn’t available just yet — please try again shortly.' },
      { status: 503 },
    )
  }
}
