/**
 * Real membership state for the customer plan card.
 *
 * Every customer surface used to render a hardcoded `plan: 'Forge Automate'`,
 * `badge: 'Early Access'` card with four features marked "Active" — identical for
 * a paying subscriber, a trialing signup and someone with no subscription at all.
 * It described an entitlement the system had never checked.
 *
 * Since the Stripe work landed, `customer_bot_subscriptions` holds the real thing
 * (status, price lookup key, current_period_end), so the card can tell the truth.
 *
 * Fails SOFT, not closed: billing lives in a different database from the trading
 * ledger, and the Live page must still render if it is unreachable. On any error
 * we return the neutral "IronForge Membership" card rather than claiming a plan.
 */
import { customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { MARKETING_TIERS, TRIAL_DAYS } from '@/lib/billing/plans'

export interface MembershipCard {
  plan: string
  badge: string
  trial?: { label: string; day: number; total_days: number; ends_label: string } | null
}

/** Shown when we genuinely do not know — never a plan name we haven't verified. */
const NEUTRAL: MembershipCard = { plan: 'IronForge Membership', badge: 'Early Access', trial: null }

interface SubRow {
  bot: string
  status: string
  price_lookup_key: string | null
  current_period_end: string | null
}

/** Statuses that mean the customer currently has access. */
const LIVE_STATUSES = new Set(['trialing', 'active', 'past_due'])

function planNameFor(rows: SubRow[]): string {
  if (rows.some((r) => r.price_lookup_key === 'both_monthly') || rows.length > 1) {
    return MARKETING_TIERS.pro.name
  }
  return MARKETING_TIERS.starter.name
}

function badgeFor(rows: SubRow[]): string {
  if (rows.some((r) => r.status === 'past_due')) return 'Payment due'
  if (rows.every((r) => r.status === 'trialing')) return 'Free trial'
  return 'Active'
}

/**
 * Build the plan card for a signed-in customer.
 * @param customerId users.id — null for operators/anonymous, which get NEUTRAL.
 */
export async function getMembership(customerId: string | null): Promise<MembershipCard> {
  if (!customerId || !isCustomersDbConfigured()) return NEUTRAL
  try {
    const rows = await customerQuery<SubRow>(
      `SELECT bot, status, price_lookup_key, current_period_end
         FROM customer_bot_subscriptions
        WHERE user_id = $1`,
      [customerId],
    )
    const live = rows.filter((r) => LIVE_STATUSES.has(r.status))
    if (live.length === 0) {
      // Known state, and it is "nothing active" — say so instead of implying a plan.
      return { plan: 'IronForge Membership', badge: rows.length > 0 ? 'Inactive' : 'No plan', trial: null }
    }

    const card: MembershipCard = { plan: planNameFor(live), badge: badgeFor(live), trial: null }

    // Trial countdown, derived from Stripe's period end rather than invented.
    const trialing = live.filter((r) => r.status === 'trialing' && r.current_period_end)
    if (trialing.length > 0 && live.every((r) => r.status === 'trialing')) {
      const ends = new Date(trialing[0].current_period_end as string)
      const msLeft = ends.getTime() - Date.now()
      const daysLeft = Math.max(0, Math.ceil(msLeft / 86_400_000))
      const day = Math.min(TRIAL_DAYS, Math.max(1, TRIAL_DAYS - daysLeft + 1))
      card.trial = {
        label: daysLeft <= 1 ? 'Trial ends today' : `${daysLeft} days left in trial`,
        day,
        total_days: TRIAL_DAYS,
        ends_label: `Ends ${ends.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`,
      }
    }
    return card
  } catch {
    return NEUTRAL
  }
}
