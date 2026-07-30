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
import { MARKETING_TIERS, TRIAL_DAYS, COMMUNITY_PLAN, isCommunityKey } from '@/lib/billing/plans'
import { TRIAL_ELIGIBLE_DAYS, trialLabel } from '@/lib/enrollment/trading-days'

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
  // Community is not a bot — it never counts toward Starter/Pro and only names the
  // plan when it is the *only* thing active.
  const botRows = rows.filter((r) => !isCommunityKey(r.bot))
  if (botRows.length === 0) return COMMUNITY_PLAN.name
  if (botRows.some((r) => r.price_lookup_key === 'both_monthly') || botRows.length > 1) {
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

    if (live.every((r) => r.status === 'trialing')) {
      // Trading-day LEDGER first. A v2 activation creates the subscription trialing
      // with a ~60-day Stripe HOLD (the ledger ends it after five ELIGIBLE trading
      // days), so deriving from current_period_end would tell that customer they have
      // two months of trial. The ledger row is the authority when one is active.
      const ledger = await customerQuery<{ eligible_days_used: string | null }>(
        `SELECT eligible_days_used::text FROM trials
          WHERE user_id = $1 AND status = 'active'
          ORDER BY started_at DESC LIMIT 1`,
        [customerId],
      ).catch(() => [] as Array<{ eligible_days_used: string | null }>)

      if (ledger[0]) {
        const used = Math.min(TRIAL_ELIGIBLE_DAYS, Math.max(0, Number(ledger[0].eligible_days_used ?? 0)))
        card.trial = {
          label: trialLabel(used),
          day: Math.min(TRIAL_ELIGIBLE_DAYS, used + 1),
          total_days: TRIAL_ELIGIBLE_DAYS,
          ends_label: 'Counts eligible trading days only',
        }
        return card
      }

      // Legacy (v1) trials: derived from Stripe's period end rather than invented.
      const trialing = live.filter((r) => r.status === 'trialing' && r.current_period_end)
      if (trialing.length > 0) {
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
    }
    return card
  } catch {
    return NEUTRAL
  }
}

/**
 * True when the customer has any active/trialing/past_due subscription — a bot OR Community.
 * Used to gate community participation: reading the feed is open (a locked preview), but
 * posting requires a live membership, which is what the $15 Community plan buys. Fails SOFT
 * (returns false) so a billing-DB outage never grants access it can't verify.
 */
export async function hasActiveMembership(customerId: string | null): Promise<boolean> {
  if (!customerId || !isCustomersDbConfigured()) return false
  try {
    const rows = await customerQuery<{ status: string }>(
      `SELECT status FROM customer_bot_subscriptions WHERE user_id = $1`,
      [customerId],
    )
    return rows.some((r) => LIVE_STATUSES.has(r.status))
  } catch {
    return false
  }
}

/**
 * True when the customer owns a STRATEGY (Spark or Flame) — not merely Community.
 *
 * Distinct from hasActiveMembership on purpose. Community buys the chat, and its page is
 * deliberately readable while signed in (the composer swaps to a join CTA on 402). The
 * Live dashboard is different: it is the strategy product, and there is nothing there for
 * someone who owns no strategy.
 *
 * This exists because "is a customer" was being answered by `/api/auth/customer-me`
 * returning ok — which only ever meant SIGNED IN. Anyone who made a free account saw
 * "Live" in the marketing nav while owning nothing. That is the same conflation of
 * "anonymous" with "signed in, nothing bought" that has now surfaced four times.
 *
 * Fails CLOSED, like hasActiveMembership: an unreadable billing DB must never advertise
 * an entitlement it cannot verify.
 */
export async function ownsStrategy(customerId: string | null): Promise<boolean> {
  if (!customerId || !isCustomersDbConfigured()) return false
  try {
    const rows = await customerQuery<{ bot: string; status: string }>(
      `SELECT bot, status FROM customer_bot_subscriptions WHERE user_id = $1`,
      [customerId],
    )
    return ownsStrategyFromRows(rows)
  } catch {
    return false
  }
}

/**
 * The predicate, split from the query so it can be tested without a database.
 *
 * A row grants Live access only when it is BOTH a strategy (not Community) AND in a
 * live status. Getting either half wrong shows the strategy dashboard to someone who
 * bought chat, or hides it from someone mid-trial.
 */
export function ownsStrategyFromRows(rows: ReadonlyArray<{ bot: string; status: string }>): boolean {
  return rows.some((r) => !isCommunityKey(r.bot) && LIVE_STATUSES.has(r.status))
}
