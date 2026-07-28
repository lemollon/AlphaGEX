import { NextRequest, NextResponse } from 'next/server'
import { verifyStripeSignature } from '@/lib/billing/stripe'
import { isCustomersDbConfigured, customerExecute, customerQuery } from '@/lib/customers-db'
import { getBotPlan, BOTH_PLAN, COMMUNITY_PLAN, isCommunityKey } from '@/lib/billing/plans'

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

  try {
    const obj = event?.data?.object ?? {}
    switch (event?.type) {
      case 'checkout.session.completed': {
        const userId = await resolveUserId(obj.metadata, obj.customer)
        const { bots, bundle } = botsFor(obj.metadata)
        if (userId && bots.length) {
          for (const bot of bots) {
            await upsertSubscription({
              userId,
              bot,
              status: 'trialing',
              subscriptionId: typeof obj.subscription === 'string' ? obj.subscription : null,
              currentPeriodEnd: null,
              priceLookupKey: bundle ? BOTH_PLAN.lookupKey : undefined,
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
          for (const bot of bots) {
            await upsertSubscription({
              userId,
              bot,
              status,
              subscriptionId: typeof obj.id === 'string' ? obj.id : null,
              currentPeriodEnd: unix(obj.current_period_end),
              priceLookupKey: bundle ? BOTH_PLAN.lookupKey : undefined,
            })
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
    console.error('[billing/webhook] handler error:', e)
    // Ack anyway — a retry storm won't help a logic bug, and the signature was valid.
  }

  return NextResponse.json({ ok: true })
}
