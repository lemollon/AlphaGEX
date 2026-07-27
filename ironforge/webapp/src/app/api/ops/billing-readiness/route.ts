import { NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { isStripeConfigured, findPriceByLookupKey } from '@/lib/billing/stripe'
import { BOT_PLANS, BOTH_PLAN, COMMUNITY_PLAN } from '@/lib/billing/plans'

/**
 * Stripe readiness + PRICE PARITY check.
 *
 * Read-only. Answers one question: if a customer clicked subscribe right now,
 * would they be charged the number the site advertises?
 *
 * This exists because the two prices live in different systems. The site renders
 * `priceMonthly` from lib/billing/plans.ts; Stripe charges whatever the Price
 * behind the matching `lookupKey` says. Nothing keeps them in step. Community
 * was just changed from $15 to $10 on the site — if the Stripe price is still
 * $15, every subscriber is overcharged and neither number looks wrong on its own.
 *
 * Run this after provisioning Stripe, and again after any price change.
 *
 * GET /api/ops/billing-readiness   (operator session required)
 */
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

interface PlanCheck {
  plan: string
  lookupKey: string
  advertised: number
  stripe: number | null
  currency: string | null
  interval: string | null
  status: 'ok' | 'price_mismatch' | 'missing_in_stripe' | 'not_monthly' | 'wrong_currency' | 'lookup_failed'
  detail?: string
}

const EXPECTED_CURRENCY = 'usd'
const EXPECTED_INTERVAL = 'month'

export async function GET() {
  const ops = await getSession()
  if (!ops.userId) {
    return NextResponse.json({ ok: false, error: 'Operator session required.' }, { status: 401 })
  }

  const secretKeySet = isStripeConfigured()
  const webhookSecretSet = !!process.env.STRIPE_WEBHOOK_SECRET?.trim()

  // Every plan the site can sell, with the number it shows for each.
  const plans: Array<{ plan: string; lookupKey: string; advertised: number }> = [
    { plan: COMMUNITY_PLAN.name, lookupKey: COMMUNITY_PLAN.lookupKey, advertised: COMMUNITY_PLAN.priceMonthly },
    ...Object.values(BOT_PLANS).map((p) => ({
      plan: p.name,
      lookupKey: p.lookupKey,
      advertised: p.priceMonthly,
    })),
    // BOTH_PLAN has no `name` field — it is the bundle, labelled 'Forge Pro' in
    // MARKETING_TIERS.
    { plan: 'Forge Pro (both bots)', lookupKey: BOTH_PLAN.lookupKey, advertised: BOTH_PLAN.priceMonthly },
  ]

  if (!secretKeySet) {
    return NextResponse.json({
      ok: false,
      ready: false,
      blocker: 'STRIPE_SECRET_KEY is not set — checkout and the billing portal return 503.',
      secretKeySet,
      webhookSecretSet,
      // Still useful unprovisioned: this is exactly what must be created in Stripe.
      required: plans.map((p) => ({
        ...p,
        stripePriceMustBe: `${p.advertised}.00 ${EXPECTED_CURRENCY.toUpperCase()} / ${EXPECTED_INTERVAL}`,
      })),
      webhookEvents: [
        'checkout.session.completed',
        'customer.subscription.created',
        'customer.subscription.updated',
        'customer.subscription.deleted',
      ],
      webhookPath: '/api/billing/webhook',
    })
  }

  const checks: PlanCheck[] = []
  for (const p of plans) {
    try {
      const price = await findPriceByLookupKey(p.lookupKey)
      if (!price) {
        checks.push({ ...p, stripe: null, currency: null, interval: null, status: 'missing_in_stripe' })
        continue
      }
      const dollars = price.unit_amount === null ? null : price.unit_amount / 100
      const interval = price.recurring?.interval ?? null
      let status: PlanCheck['status'] = 'ok'
      let detail: string | undefined

      if (price.currency?.toLowerCase() !== EXPECTED_CURRENCY) {
        status = 'wrong_currency'
        detail = `Stripe price is in ${price.currency}, site assumes ${EXPECTED_CURRENCY}.`
      } else if (interval !== EXPECTED_INTERVAL) {
        status = 'not_monthly'
        detail = `Stripe price recurs per ${interval ?? 'never'}, site advertises /month.`
      } else if (dollars !== p.advertised) {
        status = 'price_mismatch'
        detail = `Site advertises $${p.advertised}/month; Stripe would charge $${dollars}/month.`
      }

      checks.push({ ...p, stripe: dollars, currency: price.currency, interval, status, detail })
    } catch (err: unknown) {
      checks.push({
        ...p,
        stripe: null,
        currency: null,
        interval: null,
        status: 'lookup_failed',
        detail: err instanceof Error ? err.message : String(err),
      })
    }
  }

  const problems = checks.filter((c) => c.status !== 'ok')
  const ready = secretKeySet && webhookSecretSet && problems.length === 0

  return NextResponse.json({
    ok: true,
    ready,
    secretKeySet,
    webhookSecretSet,
    ...(webhookSecretSet
      ? {}
      : { warning: 'STRIPE_WEBHOOK_SECRET is not set — subscriptions will not activate after checkout.' }),
    summary: ready
      ? 'Every advertised price matches Stripe.'
      : `${problems.length} of ${checks.length} plans would not charge what the site advertises.`,
    checks,
  })
}
