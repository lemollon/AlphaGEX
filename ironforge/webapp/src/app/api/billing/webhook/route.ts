import { NextRequest, NextResponse } from 'next/server'
import { verifyStripeSignature } from '@/lib/billing/stripe'
import { isCustomersDbConfigured, customerExecute, customerQuery } from '@/lib/customers-db'
import { getBotPlan } from '@/lib/billing/plans'

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
}) {
  const plan = getBotPlan(opts.bot)
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
    [opts.userId, opts.bot, opts.status, opts.subscriptionId, plan?.lookupKey ?? null, opts.currentPeriodEnd],
  )
}

export async function POST(req: NextRequest) {
  const secret = process.env.STRIPE_WEBHOOK_SECRET
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
        const bot = obj.metadata?.bot
        if (userId && bot && getBotPlan(bot)) {
          await upsertSubscription({
            userId,
            bot,
            status: 'trialing',
            subscriptionId: typeof obj.subscription === 'string' ? obj.subscription : null,
            currentPeriodEnd: null,
          })
        }
        break
      }
      case 'customer.subscription.updated':
      case 'customer.subscription.created':
      case 'customer.subscription.deleted': {
        const userId = await resolveUserId(obj.metadata, obj.customer)
        const bot = obj.metadata?.bot
        if (userId && bot && getBotPlan(bot)) {
          const status = event.type === 'customer.subscription.deleted' ? 'canceled' : String(obj.status ?? 'active')
          await upsertSubscription({
            userId,
            bot,
            status,
            subscriptionId: typeof obj.id === 'string' ? obj.id : null,
            currentPeriodEnd: unix(obj.current_period_end),
          })
        }
        break
      }
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
