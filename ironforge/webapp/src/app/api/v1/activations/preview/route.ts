import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured } from '@/lib/customers-db'
import { loadActivationContext } from '@/lib/enrollment/context'
import { evaluateActivation } from '@/lib/enrollment/activation'
import { PREVIEW_TTL_MS } from '@/lib/enrollment/preview'
import { errorEnvelope, statusFor, redactProviderError } from '@/lib/enrollment/errors'
import { BOT_PLANS } from '@/lib/billing/plans'
import { TRIAL_ELIGIBLE_DAYS } from '@/lib/enrollment/trading-days'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * POST /api/v1/activations/preview — the immutable review snapshot (§3 ACT-01, §6).
 *
 * "Display immutable activation snapshot before consent." This returns exactly what the
 * customer is about to authorize — which account, which strategy, how much capital, which
 * agreement versions — together with the hash that binds their consent to it.
 *
 * Two deliberate choices:
 *
 *  BLOCKERS ARE NOT AN ERROR HERE. A customer partway through setup should see the whole
 *  picture, including what is still missing, rather than an opaque refusal. Activation is
 *  where blockers are fatal; preview is where they are INFORMATION. It returns 200 with
 *  `can_activate: false`.
 *
 *  READ-ONLY. Nothing is stored. The hash is derived from live state on both sides, so a
 *  stale preview is detected by recomputation at activation rather than by trusting a
 *  saved row — there is no preview record to fall out of date.
 */
export async function POST(req: NextRequest) {
  const session = await getCustomerSession()
  if (!session.customerId) {
    const e = errorEnvelope('UNAUTHORIZED', 'Please sign in to continue.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  if (!isCustomersDbConfigured()) {
    const e = errorEnvelope('NOT_CONFIGURED', 'Setup is temporarily unavailable.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }

  try {
    const body = (await req.json().catch(() => ({}))) as { config_id?: unknown }
    const ctx = await loadActivationContext(session.customerId, String(body.config_id ?? ''))
    if (!ctx) {
      const e = errorEnvelope('FORBIDDEN', 'That configuration is not available.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    // The acknowledgments are given on the review screen ITSELF, so they are not yet
    // true at preview time. Passing them as satisfied keeps the blocker list about what
    // the customer must go fix elsewhere, not about the checkbox in front of them.
    const decision = evaluateActivation({
      ...ctx.inputs,
      riskAcknowledged: true,
      authorizationAcknowledged: true,
      previewCurrent: true,
    })

    const plan = BOT_PLANS[ctx.config.agent_code as 'spark' | 'flame']

    return NextResponse.json({
      preview_hash: ctx.hash,
      expires_in_seconds: Math.floor(PREVIEW_TTL_MS / 1000),
      snapshot: {
        agent: ctx.config.agent_code,
        rule_version: ctx.config.rule_version,
        // Masked only — the full account number never leaves the encrypted column (§8).
        account_mask: ctx.snapshot.accountMask,
        max_deployment_cents: ctx.snapshot.maxDeploymentCents,
        buying_power_cents: ctx.snapshot.buyingPowerCents,
        legal_versions: ctx.snapshot.legalVersions,
        plan: plan ? { name: plan.productName, price_monthly: plan.priceMonthly, interval: 'month' } : null,
        trial: { eligible_days_total: TRIAL_ELIGIBLE_DAYS, counts: 'eligible trading days' },
      },
      can_activate: decision.ok,
      blockers: decision.blockers,
    })
  } catch (e) {
    const env = redactProviderError('v1/activations/preview', e, 'INTERNAL', 'Could not build your review. Please try again.')
    return NextResponse.json(env, { status: statusFor(env.code) })
  }
}
