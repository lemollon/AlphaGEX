/**
 * The membership response builder behind GET /api/billing/membership — extracted so
 * POST /api/billing/apple/verify can hand back the identical shape after writing an Apple
 * subscription row, instead of a second, driftable copy of this query. See that route's
 * comment for why: what a customer pays and when they're billed next must read the same
 * regardless of which billing rail wrote the row.
 */

import { customerQuery } from '@/lib/customers-db'
import { BOT_PLANS, BOTH_PLAN, COMMUNITY_PLAN, COMMUNITY_KEY, type BotSlug } from '@/lib/billing/plans'
import { TRIAL_ELIGIBLE_DAYS } from '@/lib/enrollment/trading-days'

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
 * One customer can hold several rows (spark, flame, community). What they PAY depends on
 * HOW the second bot was bought: a legacy both_monthly bundle subscription (one Stripe
 * sub covering both bots, $75) still exists for customers who bought it before 2026-10-04.
 * Every NEW second-bot purchase since then is its own full-price subscription — two
 * separate $50 subs, summing to $100, never the $75 bundle rate (Leron, binding).
 */
function resolvePlan(rows: SubRow[]): { name: string; priceMonthly: number } {
  const bots = rows.map((r) => r.bot).filter((b): b is BotSlug => b === 'spark' || b === 'flame')
  const hasCommunity = rows.some((r) => r.bot === COMMUNITY_KEY)
  const isLegacyBundle = rows.some((r) => r.price_lookup_key === BOTH_PLAN.lookupKey)

  if (bots.length >= 2) {
    if (isLegacyBundle) {
      return { name: 'Forge Automate — Spark + Flame', priceMonthly: BOTH_PLAN.priceMonthly }
    }
    const total = bots.reduce((sum, b) => sum + BOT_PLANS[b].priceMonthly, 0)
    return { name: `Forge Automate — ${bots.map((b) => BOT_PLANS[b].name).join(' + ')}`, priceMonthly: total }
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
    /** db-states "Trial ending ... Banner 1 trading day before trial end" (gap audit
     *  #212), mirrored from lib/live/membership.ts's web card so the app and the web
     *  dashboard agree on the same trading-day ledger, not two different clocks. */
    trial_ending_soon: boolean
    /**
     * Per-agent breakdown (gap audit MISSING — "One blended total for multi-agent
     * owners, no per-bot breakdown"). resolvePlan()'s blended `plan`/`price_monthly`
     * above stays as-is for the single-line summary; this is the itemized view for a
     * customer who owns more than one agent, each with its own price and trial clock.
     */
    agents: Array<{
      bot: string
      name: string
      price_monthly: number
      status: string
      badge: string
      next_billing_date: string | null
      trial_ending_soon: boolean
    }>
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

  let trialEndingSoon = false
  if (status === 'trialing') {
    const ledger = await customerQuery<{ eligible_days_used: string | null }>(
      `SELECT eligible_days_used::text FROM trials
        WHERE user_id = $1 AND status = 'active'
        ORDER BY started_at DESC LIMIT 1`,
      [customerId],
    ).catch(() => [] as Array<{ eligible_days_used: string | null }>)
    if (ledger[0]) {
      const used = Math.min(TRIAL_ELIGIBLE_DAYS, Math.max(0, Number(ledger[0].eligible_days_used ?? 0)))
      trialEndingSoon = TRIAL_ELIGIBLE_DAYS - used <= 1
    }
  }

  // Per-agent breakdown — one row per owned trading bot, each with ITS OWN trial
  // clock (trials.agent_code scopes the ledger per bot; resolvePlan()'s blended
  // total above has no concept of "this one's trial ends tomorrow but that one
  // just started").
  const agents = await Promise.all(
    live
      .filter((r): r is SubRow & { bot: BotSlug } => r.bot === 'spark' || r.bot === 'flame')
      .map(async (r) => {
        const plan = BOT_PLANS[r.bot]
        let agentTrialEndingSoon = false
        if (r.status === 'trialing') {
          const ledger = await customerQuery<{ eligible_days_used: string | null }>(
            `SELECT eligible_days_used::text FROM trials
              WHERE user_id = $1 AND agent_code = $2 AND status = 'active'
              ORDER BY started_at DESC LIMIT 1`,
            [customerId, r.bot],
          ).catch(() => [] as Array<{ eligible_days_used: string | null }>)
          if (ledger[0]) {
            const used = Math.min(TRIAL_ELIGIBLE_DAYS, Math.max(0, Number(ledger[0].eligible_days_used ?? 0)))
            agentTrialEndingSoon = TRIAL_ELIGIBLE_DAYS - used <= 1
          }
        }
        return {
          bot: r.bot,
          name: plan.name,
          price_monthly: plan.priceMonthly,
          status: r.status,
          badge: badgeFor(r.status),
          next_billing_date: r.current_period_end,
          trial_ending_soon: agentTrialEndingSoon,
        }
      }),
  )

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
      trial_ending_soon: trialEndingSoon,
      agents,
    },
  }
}
