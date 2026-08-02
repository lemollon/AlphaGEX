import { NextRequest, NextResponse } from 'next/server'
import { publicOrigin } from '@/lib/public-origin'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { billingReturn, type BillingClient } from '@/lib/mobile/deep-link'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'
import { isStripeConfigured, createBillingPortalSession } from '@/lib/billing/stripe'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Opens the Stripe Customer Portal for the signed-in customer (change plan /
 * update card / cancel / receipts) and returns its hosted url. Customer-session
 * guarded. Returns 409 with reason 'no_subscription' when the user has never
 * checked out (no Stripe customer yet) so the UI can point them at plans instead;
 * 503 until Stripe + the portal are provisioned, so the Billing page degrades cleanly.
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

    const { url } = await createBillingPortalSession({
      customerId: stripeCustomerId,
      returnUrl: billingReturn(publicOrigin(req), client, '/account/billing'),
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
