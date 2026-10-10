import { NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured } from '@/lib/customers-db'
import { buildMembershipResponse } from '@/lib/billing/membership'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * GET /api/billing/membership — what this customer actually pays, and when next.
 *
 * APP-038 asks for plan name, status, monthly price and next billing date. None of that
 * was reachable: LiveSummary.membership is a hardcoded {plan:'IronForge Membership',
 * badge:'Early Access'} with a comment saying no billing state exists yet — but it does.
 * `customer_bot_subscriptions` is written by the verified Stripe webhook (and, as of the
 * Apple IAP rail, the verified StoreKit transaction/notification path too) and is, per
 * customers-db.ts's own note, "the spec's own authority for membership state". It carries
 * status, provider, price_lookup_key and current_period_end. This reads it.
 *
 * The PRICE comes from lib/billing/plans.ts, the same catalogue checkout prices from, so
 * a displayed number cannot drift from what Stripe (or Apple, same USD prices) bills. It
 * is not stored per-row.
 *
 * Degrades to `{ok:true, membership:null}` rather than erroring when billing is not
 * provisioned — a customer with no subscription is a normal state, not a failure.
 *
 * The query + shaping logic lives in lib/billing/membership.ts (buildMembershipResponse) so
 * POST /api/billing/apple/verify can return the exact same payload after writing a row.
 */
export async function GET() {
  const identity = await getCustomerIdentity()
  const customerId = identity?.customerId ?? null
  if (!customerId) return NextResponse.json({ ok: false }, { status: 401 })

  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: true, configured: false, membership: null })
  }

  try {
    return NextResponse.json(await buildMembershipResponse(customerId))
  } catch (e) {
    console.error('[billing/membership] failed:', e)
    return NextResponse.json({ ok: false, error: 'Could not load your membership.' }, { status: 500 })
  }
}
