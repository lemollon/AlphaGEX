import { NextRequest, NextResponse } from 'next/server'
import { verifyStripeSignature } from '@/lib/billing/stripe'
import { isCustomersDbConfigured, customerExecute, customerQuery } from '@/lib/customers-db'
import { getBotPlan, BOTH_PLAN, COMMUNITY_PLAN, MARKETING_TIERS, isCommunityKey } from '@/lib/billing/plans'
import { isUuid } from '@/lib/enrollment/ids'
import { enqueueCrmEvent } from '@/lib/crm/outbox'
import type { CrmEventType } from '@/lib/crm/events'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Stripe webhook — keeps customer_bot_subscriptions in sync with Stripe. Verifies the signature
 * against STRIPE_WEBHOOK_SECRET (no session; Stripe is the caller). Handles the subscription
 * lifecycle: checkout completion, status changes, and cancellation. Unrecognised events are ack'd
 * with 200 so Stripe doesn't retry them.
 */

function unix(ts: unknown): string | null {
  return typeof ts === 'number' && ts > 0 ? new Date(ts * 1000).toISOString() : null
}

async function resolveUserId(meta: Record<string, any> | undefined, customerId: string | undefined): Promise<string | null> {
  const fromMeta = meta?.ironforge_user_id
  if (typeof fromMeta === 'string' && fromMeta) return fromMeta
  if (customerId) {
    const rows = await customerQuery<{ id: string }>(
      `SELECT id FROM users WHERE stripe_customer_id = $1 LIMIT 1`,
      [customerId],
    )
    return rows[0]?.id ?? null
  }
  return null
}

async function upsertSubscription(opts: {
  userId: string
  bot: string
  status: string
  subscriptionId: string | null
  currentPeriodEnd: string | null
  /** Overrides the derived single-bot lookup key — set to 'both_monthly' for bundle rows. */
  priceLookupKey?: string | null
}) {
  const derivedKey = isCommunityKey(opts.bot) ? COMMUNITY_PLAN.lookupKey : getBotPlan(opts.bot)?.lookupKey
  const lookupKey = opts.priceLookupKey ?? derivedKey ?? null
  await customerExecute(
    `INSERT INTO customer_bot_subscriptions
       (user_id, bot, status, stripe_subscription_id, price_lookup_key, current_period_end, updated_at)
     VALUES ($1, $2, $3, $4, $5, $6, now())
     ON CONFLICT (user_id, bot) DO UPDATE SET
       status = EXCLUDED.status,
       stripe_subscription_id = COALESCE(EXCLUDED.stripe_subscription_id, customer_bot_subscriptions.stripe_subscription_id),
       price_lookup_key = COALESCE(EXCLUDED.price_lookup_key, customer_bot_subscriptions.price_lookup_key),
       current_period_end = COALESCE(EXCLUDED.current_period_end, customer_bot_subscriptions.current_period_end),
       updated_at = now()`,
    [opts.userId, opts.bot, opts.status, opts.subscriptionId, lookupKey, opts.currentPeriodEnd],
  )
}

/**
 * The bots a subscription grants. A single-bot sub carries `metadata.bot`; a bundle sub (created by
 * the second-bot upgrade) carries `metadata.bots` as a CSV. The bundle case must fan out to BOTH
 * bot rows so a subscription.deleted/past_due on the one bundle sub correctly updates both.
 */
function isKnownPlan(v: unknown): v is string {
  return typeof v === 'string' && (Boolean(getBotPlan(v)) || isCommunityKey(v))
}

function botsFor(meta: Record<string, any> | undefined): { bots: string[]; bundle: boolean } {
  const csv = meta?.bots
  if (typeof csv === 'string' && csv.includes(',')) {
    const bots = csv.split(',').map((b) => b.trim()).filter((b) => getBotPlan(b))
    if (bots.length > 1) return { bots, bundle: true }
  }
  // Single entitlement — a bot (spark/flame) or the standalone Community plan.
  const single = meta?.bot
  return { bots: isKnownPlan(single) ? [single] : [], bundle: false }
}

// ── CRM outbox emitters ──────────────────────────────────────────────────────
// Fire-and-forget mirrors of the membership state this handler already computed and wrote to
// customer_bot_subscriptions. enqueueCrmEvent never throws and never blocks — a CRM outage must
// never affect Stripe's view of this webhook (audit C5's whole point).

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

/** Which bots (spark/flame/community) a given Stripe subscription currently grants. */
async function botsForSubscription(userId: string, subscriptionId: string): Promise<{ bots: string[]; bundle: boolean }> {
  const rows = await customerQuery<{ bot: string; price_lookup_key: string | null }>(
    `SELECT bot, price_lookup_key FROM customer_bot_subscriptions WHERE user_id = $1 AND stripe_subscription_id = $2`,
    [userId, subscriptionId],
  )
  return { bots: rows.map((r) => r.bot), bundle: rows.some((r) => r.price_lookup_key === BOTH_PLAN.lookupKey) }
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

interface MembershipEventInput {
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
 * fallback only fires before Stripe assigns one, and it is what lets a returning customer's new
 * subscription create a NEW membership record rather than overwrite history (AC-CRM-013).
 */
async function emitMembershipEvent(input: MembershipEventInput): Promise<void> {
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

export async function POST(req: NextRequest) {
  const secret = process.env.STRIPE_WEBHOOK_SECRET?.trim()
  const raw = await req.text()
  const sig = req.headers.get('stripe-signature')

  if (!secret || !verifyStripeSignature(raw, sig, secret)) {
    return NextResponse.json({ ok: false, error: 'invalid signature' }, { status: 400 })
  }
  if (!isCustomersDbConfigured()) {
    // Signature was valid; ack so Stripe doesn't retry, but we can't persist yet.
    return NextResponse.json({ ok: true, stored: false })
  }

  let event: any
  try {
    event = JSON.parse(raw)
  } catch {
    return NextResponse.json({ ok: false, error: 'bad payload' }, { status: 400 })
  }

  // Replay/dedupe guard (audit C5): Stripe delivers at-least-once and out of order.
  // The INSERT is the claim — a duplicate delivery matches the primary key and is
  // acknowledged without re-running the handler, so a retry of an already-applied
  // event can never regress a subscription row that later events (or the checkout
  // route's immediate write) have advanced.
  const eventId = typeof event?.id === 'string' ? event.id : null
  if (eventId) {
    const claimed = await customerExecute(
      `INSERT INTO stripe_webhook_events (event_id, event_type) VALUES ($1, $2)
       ON CONFLICT (event_id) DO NOTHING`,
      [eventId, String(event?.type ?? 'unknown')],
    ).catch(() => 1) // if the guard table itself is unavailable, fall through and process
    if (claimed === 0) {
      // Seen before. Successfully processed → ack the duplicate. Previously FAILED
      // (dead-letter row, processed_at NULL) → this is Stripe's retry: process again.
      const prior = await customerQuery<{ processed_at: string | null }>(
        `SELECT processed_at FROM stripe_webhook_events WHERE event_id = $1 LIMIT 1`,
        [eventId],
      ).catch(() => [] as Array<{ processed_at: string | null }>)
      if (prior[0]?.processed_at) {
        return NextResponse.json({ ok: true, duplicate: true })
      }
    }
  }

  try {
    const obj = event?.data?.object ?? {}
    switch (event?.type) {
      case 'checkout.session.completed': {
        const userId = await resolveUserId(obj.metadata, obj.customer)

        // Setup-mode sessions capture a card at $0 — NO subscription exists and none may
        // be written here. Without this guard a setup session whose metadata carried a
        // bot would fabricate a 'trialing' entitlement row with a NULL subscription id,
        // and ownsStrategy()/hasActiveMembership() treat 'trialing' as live. The only
        // thing a completed setup session means is "payment method saved": advance the
        // enrollment so the funnel resumes at brokerage setup. Guarded on
        // billing_pending so a replayed event can never rewind a further-along record.
        if (obj.mode === 'setup') {
          // isUuid guard: a non-UUID would make Postgres RAISE on the cast (a 500-class
          // handler error), not merely match zero rows.
          const enrollmentId = typeof obj.metadata?.enrollment_id === 'string' ? obj.metadata.enrollment_id : null
          if (userId && enrollmentId && isUuid(enrollmentId) && isUuid(userId)) {
            await customerExecute(
              `UPDATE enrollments
                  SET status = 'setup_required', current_step = 'setup', updated_at = now()
                WHERE id = $1 AND user_id = $2 AND status = 'billing_pending'`,
              [enrollmentId, userId],
            )
          }
          break
        }

        const { bots, bundle } = botsFor(obj.metadata)
        if (userId && bots.length) {
          const subscriptionId = typeof obj.subscription === 'string' ? obj.subscription : null
          for (const bot of bots) {
            await upsertSubscription({
              userId,
              bot,
              status: 'trialing',
              subscriptionId,
              currentPeriodEnd: null,
              priceLookupKey: bundle ? BOTH_PLAN.lookupKey : undefined,
            })
          }
          if (eventId) {
            await emitMembershipEvent({
              eventId,
              eventType: 'crm.stripe_customer_created',
              userId,
              bots,
              bundle,
              status: 'trialing',
              stripeCustomerId: typeof obj.customer === 'string' ? obj.customer : null,
              subscriptionId,
              startDate: unix(event.created) ?? new Date().toISOString(),
            })
          }
        }
        break
      }
      case 'customer.subscription.updated':
      case 'customer.subscription.created':
      case 'customer.subscription.deleted': {
        const userId = await resolveUserId(obj.metadata, obj.customer)
        const { bots, bundle } = botsFor(obj.metadata)
        if (userId && bots.length) {
          const status = event.type === 'customer.subscription.deleted' ? 'canceled' : String(obj.status ?? 'active')
          const subscriptionId = typeof obj.id === 'string' ? obj.id : null
          for (const bot of bots) {
            await upsertSubscription({
              userId,
              bot,
              status,
              subscriptionId,
              currentPeriodEnd: unix(obj.current_period_end),
              priceLookupKey: bundle ? BOTH_PLAN.lookupKey : undefined,
            })
          }
          if (eventId) {
            const stripeCustomerId = typeof obj.customer === 'string' ? obj.customer : null
            if (event.type === 'customer.subscription.created') {
              await emitMembershipEvent({
                eventId,
                eventType: 'crm.stripe_customer_created',
                userId,
                bots,
                bundle,
                status,
                stripeCustomerId,
                subscriptionId,
                startDate: unix(obj.start_date) ?? unix(event.created),
              })
            } else if (event.type === 'customer.subscription.deleted') {
              await emitMembershipEvent({
                eventId,
                eventType: 'crm.membership_canceled',
                userId,
                bots,
                bundle,
                status,
                stripeCustomerId,
                subscriptionId,
                cancellationDate: unix(obj.canceled_at) ?? unix(event.created),
              })
            } else if (status === 'trialing' || status === 'active') {
              await emitMembershipEvent({
                eventId,
                eventType: 'crm.subscription_active',
                userId,
                bots,
                bundle,
                status,
                stripeCustomerId,
                subscriptionId,
              })
            }
          }
        }
        break
      }
      // ── Invoice lifecycle (Enrollment spec §7) ──────────────────────────────
      // These were missing, and their absence had a real consequence: NOTHING ever
      // wrote `past_due`. The activation predicate refuses to open new trading for a
      // past_due membership (§11, "Payment fails after trial → set past_due; pause new
      // orders"), so without these events that rule could never fire — a customer whose
      // card failed kept full trading authority until the subscription was cancelled
      // outright, days later.
      //
      // Subscription status is still Stripe's word: we read obj.subscription's status
      // via the subscription events too, but invoice events are what arrive FIRST on a
      // failed charge, so they are the earliest safe moment to stop new orders.
      case 'invoice.payment_failed': {
        const userId = await resolveUserId(obj.metadata, obj.customer)
        const subId = typeof obj.subscription === 'string' ? obj.subscription : null
        if (userId && subId) {
          // Mark every bot on this subscription past_due. Scoped by subscription id so a
          // customer with two separate subscriptions only has the failing one paused.
          await customerExecute(
            `UPDATE customer_bot_subscriptions
                SET status = 'past_due', updated_at = now()
              WHERE user_id = $1 AND stripe_subscription_id = $2
                AND status IN ('trialing', 'active')`,
            [userId, subId],
          )
          console.warn(`[billing/webhook] invoice.payment_failed → past_due for sub ${subId}`)
          if (eventId) {
            const { bots, bundle } = await botsForSubscription(userId, subId)
            if (bots.length) {
              await emitMembershipEvent({
                eventId,
                eventType: 'crm.subscription_active',
                userId,
                bots,
                bundle,
                status: 'past_due',
                stripeCustomerId: typeof obj.customer === 'string' ? obj.customer : null,
                subscriptionId: subId,
              })
            }
          }
        }
        break
      }
      case 'invoice.paid': {
        // Recovery: a successful invoice clears past_due. Only lifts a past_due row —
        // it must never resurrect a canceled subscription, which is a different decision
        // made by the subscription events.
        const userId = await resolveUserId(obj.metadata, obj.customer)
        const subId = typeof obj.subscription === 'string' ? obj.subscription : null
        if (userId && subId) {
          await customerExecute(
            `UPDATE customer_bot_subscriptions
                SET status = 'active', updated_at = now()
              WHERE user_id = $1 AND stripe_subscription_id = $2
                AND status = 'past_due'`,
            [userId, subId],
          )
          if (eventId) {
            const { bots, bundle } = await botsForSubscription(userId, subId)
            if (bots.length) {
              await emitMembershipEvent({
                eventId,
                eventType: 'crm.subscription_active',
                userId,
                bots,
                bundle,
                status: 'active',
                stripeCustomerId: typeof obj.customer === 'string' ? obj.customer : null,
                subscriptionId: subId,
              })
            }
          }
        }
        break
      }
      case 'setup_intent.succeeded':
        // Automate collects a payment method BEFORE any subscription exists (§7), so
        // there is no subscription row to touch yet. Acknowledged explicitly rather than
        // falling into `default` so the handled-event list matches the spec and a reader
        // can see this was considered, not missed.
        break

      default:
        // Ignore unhandled event types.
        break
    }
  } catch (e) {
    // Audit C5: this used to ack 200 on ANY handler error, permanently dropping the
    // entitlement update (Stripe never retries a 200). A transient DB failure is the
    // COMMON case, so: record the failure on the event row (the dead-letter), release
    // the dedupe claim, and return 500 so Stripe retries with backoff. A genuine logic
    // bug will exhaust Stripe's retry schedule and stop on its own — visible in the
    // dead-letter row rather than silently swallowed.
    const msg = e instanceof Error ? e.message : String(e)
    console.error('[billing/webhook] handler error:', e)
    if (eventId) {
      await customerExecute(
        `UPDATE stripe_webhook_events SET error = $2, processed_at = NULL WHERE event_id = $1`,
        [eventId, msg.slice(0, 500)],
      ).catch(() => {})
    }
    return NextResponse.json({ ok: false, error: 'handler failed — will retry' }, { status: 500 })
  }

  if (eventId) {
    await customerExecute(
      `UPDATE stripe_webhook_events SET processed_at = now() WHERE event_id = $1`,
      [eventId],
    ).catch(() => {})
  }

  return NextResponse.json({ ok: true })
}
