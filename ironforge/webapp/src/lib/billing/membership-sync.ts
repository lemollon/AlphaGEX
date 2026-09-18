/**
 * Subscription row upsert + CRM membership event emission — shared by every writer of
 * customer_bot_subscriptions (Stripe webhook, Apple verify, Apple server notifications).
 * Extracted from what was originally Stripe-only logic inline in
 * app/api/billing/webhook/route.ts (Apple In-App Purchase / Guideline 3.1.1) so the Apple
 * rail calls the SAME functions instead of a parallel copy that could drift — a subscription
 * row and Attio's membership view must never disagree about what a customer owns, whichever
 * rail (Stripe or Apple) wrote it.
 */

import { customerExecute, customerQuery } from '@/lib/customers-db'
import { getBotPlan, COMMUNITY_PLAN, MARKETING_TIERS, isCommunityKey } from '@/lib/billing/plans'
import { enqueueCrmEvent } from '@/lib/crm/outbox'
import type { CrmEventType } from '@/lib/crm/events'

export type SubscriptionProvider = 'stripe' | 'apple'

export interface UpsertSubscriptionInput {
  userId: string
  bot: string
  status: string
  /** Defaults to 'stripe' — every call site before Apple existed implicitly meant Stripe. */
  provider?: SubscriptionProvider
  stripeSubscriptionId?: string | null
  appleOriginalTransactionId?: string | null
  currentPeriodEnd: string | null
  /** Overrides the derived single-bot lookup key — set to 'both_monthly' for bundle rows. */
  priceLookupKey?: string | null
}

export async function upsertSubscription(opts: UpsertSubscriptionInput): Promise<void> {
  const derivedKey = isCommunityKey(opts.bot) ? COMMUNITY_PLAN.lookupKey : getBotPlan(opts.bot)?.lookupKey
  const lookupKey = opts.priceLookupKey ?? derivedKey ?? null
  const provider = opts.provider ?? 'stripe'
  await customerExecute(
    `INSERT INTO customer_bot_subscriptions
       (user_id, bot, status, provider, stripe_subscription_id, apple_original_transaction_id, price_lookup_key, current_period_end, updated_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
     ON CONFLICT (user_id, bot) DO UPDATE SET
       status = EXCLUDED.status,
       provider = EXCLUDED.provider,
       stripe_subscription_id = COALESCE(EXCLUDED.stripe_subscription_id, customer_bot_subscriptions.stripe_subscription_id),
       apple_original_transaction_id = COALESCE(EXCLUDED.apple_original_transaction_id, customer_bot_subscriptions.apple_original_transaction_id),
       price_lookup_key = COALESCE(EXCLUDED.price_lookup_key, customer_bot_subscriptions.price_lookup_key),
       current_period_end = COALESCE(EXCLUDED.current_period_end, customer_bot_subscriptions.current_period_end),
       updated_at = now()`,
    [
      opts.userId,
      opts.bot,
      opts.status,
      provider,
      opts.stripeSubscriptionId ?? null,
      opts.appleOriginalTransactionId ?? null,
      lookupKey,
      opts.currentPeriodEnd,
    ],
  )
}

interface UserBasic {
  email: string
  first_name: string
  last_name: string
}

async function getUserBasic(userId: string): Promise<UserBasic | null> {
  const rows = await customerQuery<UserBasic>(
    `SELECT email, first_name, last_name FROM users WHERE id = $1 LIMIT 1`,
    [userId],
  )
  return rows[0] ?? null
}

/** Internal trialing|active|past_due|canceled|incomplete -> CRM Membership Status. */
function membershipStatusLabel(status: string): string {
  if (status === 'trialing' || status === 'active') return 'Active'
  if (status === 'past_due') return 'Past Due'
  if (status === 'canceled') return 'Canceled'
  return 'Pending' // incomplete, and anything else we don't recognize
}

/** 'Billing Complete' on activation, 'Canceled' on cancellation. Nothing else moves lifecycle here — a
 * past_due invoice pauses billing but is not a lifecycle transition, and 'Paused' is never emitted here. */
function membershipLifecycleFor(status: string): string | undefined {
  if (status === 'trialing' || status === 'active') return 'Billing Complete'
  if (status === 'canceled') return 'Canceled'
  return undefined
}

function membershipBotLabel(bots: string[], bundle: boolean): string {
  if (bundle) return 'Spark + Flame Bundle'
  const bot = bots[0]
  if (!bot || isCommunityKey(bot)) return '—'
  return getBotPlan(bot)?.name ?? '—'
}

function membershipPlanLabel(bots: string[], bundle: boolean): string {
  if (!bundle && bots[0] && isCommunityKey(bots[0])) return COMMUNITY_PLAN.name
  return MARKETING_TIERS.starter.name
}

export interface MembershipEventInput {
  eventId: string
  eventType: CrmEventType
  userId: string
  bots: string[]
  bundle: boolean
  status: string
  stripeCustomerId?: string | null
  subscriptionId?: string | null
  startDate?: string | null
  cancellationDate?: string | null
}

/**
 * membershipId is the Stripe subscription id when one exists, else `${userId}:${bot}` — the
 * fallback fires before Stripe assigns one, and for a provider that never has a Stripe
 * subscription id at all (Apple). It's what lets a returning customer's new subscription
 * create a NEW membership record rather than overwrite history (AC-CRM-013).
 */
export async function emitMembershipEvent(input: MembershipEventInput): Promise<void> {
  const user = await getUserBasic(input.userId)
  if (!user) return
  const membershipId = input.subscriptionId ?? `${input.userId}:${input.bundle ? 'both' : input.bots[0] ?? 'unknown'}`
  await enqueueCrmEvent({
    eventId: input.eventId,
    eventType: input.eventType,
    userId: input.userId,
    payload: {
      email: user.email,
      firstName: user.first_name,
      lastName: user.last_name,
      ironforgeUserId: input.userId,
      membershipId,
      plan: membershipPlanLabel(input.bots, input.bundle),
      bot: membershipBotLabel(input.bots, input.bundle),
      membershipStatus: membershipStatusLabel(input.status),
      stripeCustomerId: input.stripeCustomerId ?? undefined,
      stripeSubscriptionId: input.subscriptionId ?? undefined,
      startDate: input.startDate ?? undefined,
      cancellationDate: input.cancellationDate ?? undefined,
      lifecycle: membershipLifecycleFor(input.status),
    },
  })
}
