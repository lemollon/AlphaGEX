import { NextRequest, NextResponse } from 'next/server'
import { publicOrigin } from '@/lib/public-origin'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import {
  isStripeConfigured,
  findPriceIdByLookupKey,
  getOrCreateCustomer,
  createSubscriptionCheckout,
} from '@/lib/billing/stripe'
import { getBotPlan, TRIAL_DAYS } from '@/lib/billing/plans'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Starts a Stripe Checkout session for a bot subscription. Customer-session-guarded. Looks up (or
 * creates) the customer's Stripe Customer, resolves the bot's Price by lookup key, and returns the
 * hosted Checkout url. The card is entered on Stripe — never on IronForge. Returns 503 until Stripe
 * is provisioned so the Open Account page degrades cleanly.
 */

interface UserRow {
  id: string
  email: string | null
  stripe_customer_id: string | null
}

export async function POST(req: NextRequest) {
  const session = await getCustomerSession()
  if (!session.customerId) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })

  let bot: string | undefined
  try {
    const body = (await req.json().catch(() => null)) as { bot?: unknown } | null
    if (body && typeof body.bot === 'string') bot = body.bot
  } catch {
    /* fall through to validation */
  }
  const plan = getBotPlan(bot)
  if (!plan) return NextResponse.json({ ok: false, error: 'Unknown bot.' }, { status: 400 })

  if (!isStripeConfigured() || !isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'Checkout is temporarily unavailable. Please try again shortly.' },
      { status: 503 },
    )
  }

  try {
    const rows = await customerQuery<UserRow>(
      `SELECT id, email, stripe_customer_id FROM users WHERE id = $1 LIMIT 1`,
      [session.customerId],
    )
    const user = rows[0]
    if (!user) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })

    const priceId = await findPriceIdByLookupKey(plan.lookupKey)
    if (!priceId) {
      // Keys set but products not created yet — treat as not-yet-available, not a hard error.
      return NextResponse.json(
        { ok: false, error: 'This plan isn’t available yet. Please try again shortly.' },
        { status: 503 },
      )
    }

    const customerId = await getOrCreateCustomer({
      existingId: user.stripe_customer_id,
      email: user.email,
      userId: user.id,
    })
    if (customerId !== user.stripe_customer_id) {
      await customerExecute(`UPDATE users SET stripe_customer_id = $2, updated_at = now() WHERE id = $1`, [
        user.id,
        customerId,
      ])
    }

    const origin = publicOrigin(req)
    const { url } = await createSubscriptionCheckout({
      customerId,
      priceId,
      userId: user.id,
      bot: plan.slug,
      trialDays: TRIAL_DAYS,
      successUrl: `${origin}${plan.liveHref}?welcome=${plan.slug}&session_id={CHECKOUT_SESSION_ID}`,
      cancelUrl: `${origin}/live/${plan.slug}/open?canceled=1`,
    })

    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'CHECKOUT_STARTED', $2)`,
      [user.id, JSON.stringify({ bot: plan.slug })],
    ).catch(() => {})

    return NextResponse.json({ ok: true, url })
  } catch (e) {
    console.error('[billing/checkout] failed:', e)
    return NextResponse.json({ ok: false, error: 'Could not start checkout. Please try again.' }, { status: 500 })
  }
}
