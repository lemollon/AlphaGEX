/**
 * Does the SIGNED-IN customer own an Ember subscription? Same source of truth
 * as GET /api/billing/entitlements (customer_bot_subscriptions, bot='ember',
 * one of LIVE_STATUSES) — duplicated here as a tiny, route-local check rather
 * than an HTTP round-trip, so GET /api/ember/trades and /api/ember/status can
 * gate server-side without depending on another route's response shape.
 */
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'

const LIVE_STATUSES = ['trialing', 'active', 'past_due']

/** Returns the owning customerId, or null if not signed in / not entitled. */
export async function resolveEmberOwner(): Promise<string | null> {
  const identity = await getCustomerIdentity()
  if (!identity?.customerId || !isCustomersDbConfigured()) return null
  try {
    const rows = await customerQuery<{ status: string }>(
      `SELECT status FROM customer_bot_subscriptions WHERE user_id = $1 AND bot = 'ember'`,
      [identity.customerId],
    )
    return rows.some((r) => LIVE_STATUSES.includes(r.status)) ? identity.customerId : null
  } catch {
    return null
  }
}
