/**
 * The membership response builder behind GET /api/billing/membership — extracted so
 * POST /api/billing/apple/verify can hand back the identical shape after writing an Apple
 * subscription row, instead of a second, driftable copy of this query. See that route's
 * comment for why: what a customer pays and when they're billed next must read the same
 * regardless of which billing rail wrote the row.
 */

import { customerQuery } from '@/lib/customers-db'
import { BOT_PLANS, BOTH_PLAN, COMMUNITY_PLAN, COMMUNITY_KEY, type BotSlug } from '@/lib/billing/plans'

const LIVE_STATUSES = ['trialing', 'active', 'past_due']

interface SubRow {
  bot: string
  status: string
  provider: string
  price_lookup_key: string | null
  current_period_end: string | null
}

/** Human status, matching the pill in UX-006. */
function badgeFor(status: string): string {
  switch (status) {
    case 'active':
      return 'Active'
    case 'trialing':
      return 'Trial'
    case 'past_due':
      return 'Payment due'
    case 'canceled':
      return 'Canceled'
    default:
      return status.charAt(0).toUpperCase() + status.slice(1)
  }
}

/**
 * One customer can hold several rows (spark, flame, community). What they PAY is not the
 * sum of the catalogue prices: two bots are the $75 bundle, not $50 + $50. So the price
 * is resolved from the set of live bot subscriptions, exactly as checkout resolves it.
 */
function resolvePlan(rows: SubRow[]): { name: string; priceMonthly: number } {
  const bots = rows.map((r) => r.bot).filter((b): b is BotSlug => b === 'spark' || b === 'flame')
  const hasCommunity = rows.some((r) => r.bot === COMMUNITY_KEY)

  if (bots.length >= 2) {
    return { name: 'Forge Automate — Spark + Flame', priceMonthly: BOTH_PLAN.priceMonthly }
  }
  if (bots.length === 1) {
    const plan = BOT_PLANS[bots[0]]
    return { name: `Forge Automate — ${plan.name}`, priceMonthly: plan.priceMonthly }
  }
  if (hasCommunity) {
    return { name: COMMUNITY_PLAN.name, priceMonthly: COMMUNITY_PLAN.priceMonthly }
  }
  return { name: 'IronForge Membership', priceMonthly: 0 }
}

export interface MembershipResponse {
  ok: true
  configured: true
  membership: {
    plan: string
    status: string
    badge: string
    price_monthly: number
    next_billing_date: string | null
    bots: string[]
    provider: 'stripe' | 'apple'
  } | null
}

/**
 * Builds the exact { ok, configured, membership } payload GET /api/billing/membership
 * returns. Callers must have already confirmed isCustomersDbConfigured() — this throws on
 * a query failure rather than degrading, same as the original inline handler did.
 */
export async function buildMembershipResponse(customerId: string): Promise<MembershipResponse> {
  const rows = await customerQuery<SubRow>(
    `SELECT bot, status, provider, price_lookup_key,
            to_char(current_period_end, 'YYYY-MM-DD') AS current_period_end
       FROM customer_bot_subscriptions
      WHERE user_id = $1`,
    [customerId],
  )

  const live = rows.filter((r) => LIVE_STATUSES.includes(r.status))
  if (live.length === 0) {
    return { ok: true, configured: true, membership: null }
  }

  const { name, priceMonthly } = resolvePlan(live)

  // The soonest upcoming renewal across the live rows — that is the date the customer
  // will actually next be charged. `null` when the rail has not written one yet, which
  // the client must render as absent rather than as "no renewal".
  const ends = live.map((r) => r.current_period_end).filter((d): d is string => !!d).sort()

  // A past_due row anywhere outranks an otherwise healthy set: it is the one state that
  // needs the customer to do something.
  const status =
    live.find((r) => r.status === 'past_due')?.status ??
    live.find((r) => r.status === 'trialing')?.status ??
    live[0].status

  return {
    ok: true,
    configured: true,
    membership: {
      plan: name,
      status,
      badge: badgeFor(status),
      price_monthly: priceMonthly,
      // Presentation-free: the client formats. Sending a preformatted string here is
      // how a date ends up rendered in the server's timezone on someone else's phone.
      next_billing_date: ends[0] ?? null,
      bots: live.map((r) => r.bot),
      // 'apple' if ANY live row was written by the Apple rail — a customer can only hold
      // one active tier at a time (one subscription group on iOS), so a mixed live set is
      // not expected in practice, but Apple wins the label if it ever happens.
      provider: live.some((r) => r.provider === 'apple') ? 'apple' : 'stripe',
    },
  }
}
