import { NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'
import { BOT_PLANS, BOTH_PLAN, COMMUNITY_PLAN, COMMUNITY_KEY, type BotSlug } from '@/lib/billing/plans'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * GET /api/billing/membership — what this customer actually pays, and when next.
 *
 * APP-038 asks for plan name, status, monthly price and next billing date. None of that
 * was reachable: LiveSummary.membership is a hardcoded {plan:'IronForge Membership',
 * badge:'Early Access'} with a comment saying no billing state exists yet — but it does.
 * `customer_bot_subscriptions` is written by the verified Stripe webhook and is, per
 * customers-db.ts's own note, "the spec's own authority for membership state". It carries
 * status, price_lookup_key and current_period_end. This reads it.
 *
 * The PRICE comes from lib/billing/plans.ts, the same catalogue checkout prices from, so
 * a displayed number cannot drift from what Stripe bills. It is not stored per-row.
 *
 * Degrades to `{ok:true, membership:null}` rather than erroring when billing is not
 * provisioned — a customer with no subscription is a normal state, not a failure.
 */
const LIVE_STATUSES = ['trialing', 'active', 'past_due']

interface SubRow {
  bot: string
  status: string
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

export async function GET() {
  const identity = await getCustomerIdentity()
  const customerId = identity?.customerId ?? null
  if (!customerId) return NextResponse.json({ ok: false }, { status: 401 })

  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: true, configured: false, membership: null })
  }

  try {
    const rows = await customerQuery<SubRow>(
      `SELECT bot, status, price_lookup_key,
              to_char(current_period_end, 'YYYY-MM-DD') AS current_period_end
         FROM customer_bot_subscriptions
        WHERE user_id = $1`,
      [customerId],
    )

    const live = rows.filter((r) => LIVE_STATUSES.includes(r.status))
    if (live.length === 0) {
      return NextResponse.json({ ok: true, configured: true, membership: null })
    }

    const { name, priceMonthly } = resolvePlan(live)

    // The soonest upcoming renewal across the live rows — that is the date the customer
    // will actually next be charged. `null` when Stripe has not written one yet, which
    // the client must render as absent rather than as "no renewal".
    const ends = live.map((r) => r.current_period_end).filter((d): d is string => !!d).sort()

    // A past_due row anywhere outranks an otherwise healthy set: it is the one state that
    // needs the customer to do something.
    const status =
      live.find((r) => r.status === 'past_due')?.status ??
      live.find((r) => r.status === 'trialing')?.status ??
      live[0].status

    return NextResponse.json({
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
      },
    })
  } catch (e) {
    console.error('[billing/membership] failed:', e)
    return NextResponse.json({ ok: false, error: 'Could not load your membership.' }, { status: 500 })
  }
}
