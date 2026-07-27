import { NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { isStripeConfigured, findPriceByLookupKey, syncPriceToAdvertised } from '@/lib/billing/stripe'
import { BOT_PLANS, BOTH_PLAN, COMMUNITY_PLAN } from '@/lib/billing/plans'

/**
 * Make Stripe charge what the site advertises.
 *
 * GET  — dry run. Reports every plan whose Stripe price disagrees with plans.ts.
 * POST — applies it.
 *
 * The companion to /api/ops/billing-readiness: that one DETECTS drift, this one
 * CORRECTS it. On 2026-07-27 readiness caught Community advertising $10 while Stripe
 * would have charged $15 — the site price was cut in #2614 and Stripe never followed.
 * Fixing that by hand means knowing that Stripe prices are immutable, so you create a
 * new price, transfer the lookup key, and archive the old one in that order.
 *
 * SAFETY — this is not a "change our pricing" tool:
 *   - The target amount is ALWAYS plans.ts. Nothing in the request body can set a
 *     price; there is no amount parameter. It can only converge Stripe toward what
 *     the site already publishes.
 *   - Operator session required, and NO public-mode bypass — unlike the read-only
 *     readiness endpoints. ironforge-legacy runs fully open; a billing WRITE must not
 *     be reachable there.
 *   - Idempotent. Already-correct plans are untouched, so re-running is safe.
 *   - Existing subscriptions are NOT repriced. Subscribers keep the price they signed
 *     up at until deliberately migrated.
 */
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

interface Target { plan: string; lookupKey: string; advertised: number }

function targets(): Target[] {
  return [
    { plan: COMMUNITY_PLAN.name, lookupKey: COMMUNITY_PLAN.lookupKey, advertised: COMMUNITY_PLAN.priceMonthly },
    ...Object.values(BOT_PLANS).map((p) => ({ plan: p.name, lookupKey: p.lookupKey, advertised: p.priceMonthly })),
    { plan: 'Forge Pro (both bots)', lookupKey: BOTH_PLAN.lookupKey, advertised: BOTH_PLAN.priceMonthly },
  ]
}

async function requireOperator() {
  const ops = await getSession()
  if (!ops.userId) {
    return NextResponse.json({ ok: false, error: 'Operator session required.' }, { status: 401 })
  }
  if (!isStripeConfigured()) {
    return NextResponse.json({ ok: false, error: 'STRIPE_SECRET_KEY is not set.' }, { status: 503 })
  }
  return null
}

export async function GET() {
  const gate = await requireOperator()
  if (gate) return gate

  const plan: Array<Record<string, unknown>> = []
  for (const t of targets()) {
    try {
      const price = await findPriceByLookupKey(t.lookupKey)
      const stripeAmount = price?.unit_amount == null ? null : price.unit_amount / 100
      plan.push({
        ...t,
        stripe: stripeAmount,
        wouldChange: price != null && stripeAmount !== t.advertised,
        note: price == null
          ? 'missing_in_stripe — create it in Stripe first; this endpoint only corrects an existing price'
          : stripeAmount === t.advertised ? 'ok' : `would create a $${t.advertised} price and move ${t.lookupKey} onto it`,
      })
    } catch (e: unknown) {
      plan.push({ ...t, stripe: null, wouldChange: false, note: `lookup_failed: ${e instanceof Error ? e.message : String(e)}` })
    }
  }
  const changes = plan.filter((p) => p.wouldChange).length
  return NextResponse.json({
    ok: true,
    dryRun: true,
    summary: changes === 0 ? 'Every plan already matches. POST would do nothing.' : `${changes} plan(s) would be corrected.`,
    plan,
    apply: 'POST this same URL to apply.',
  })
}

export async function POST() {
  const gate = await requireOperator()
  if (gate) return gate

  const results: Array<Record<string, unknown>> = []
  for (const t of targets()) {
    try {
      results.push({ plan: t.plan, ...(await syncPriceToAdvertised(t.lookupKey, t.advertised)) })
    } catch (e: unknown) {
      // A throw here means we do NOT know how far the write got — syncPriceToAdvertised
      // reports partial success itself, so anything reaching this handler failed before
      // writing OR failed in a way we cannot classify. Never claim it was a no-op.
      results.push({
        plan: t.plan, lookupKey: t.lookupKey, changed: false, advertised: t.advertised,
        wasAmount: null, failed: true,
        detail: `FAILED: ${e instanceof Error ? e.message : String(e)}`,
      })
    }
  }

  const changed = results.filter((r) => r.changed)
  const failed = results.filter((r) => r.failed)
  const warnings = results.filter((r) => r.warning)

  // "Nothing to do" is only honest when nothing changed AND nothing failed. Reporting a
  // no-op over a failure is how a partial billing change gets missed.
  const summary = failed.length > 0
    ? `${failed.length} plan(s) FAILED${changed.length ? `, ${changed.length} corrected` : ''} — read results and re-run.`
    : changed.length === 0
      ? 'Nothing to do — every plan already matched.'
      : `Corrected ${changed.length} plan(s). Re-run /api/ops/billing-readiness to confirm.`

  return NextResponse.json({
    ok: failed.length === 0,
    changedCount: changed.length,
    failedCount: failed.length,
    ...(warnings.length ? { warnings: warnings.map((w) => `${w.plan}: ${w.warning}`) } : {}),
    summary,
    results,
  })
}
