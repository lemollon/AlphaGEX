import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured, customerTransaction } from '@/lib/customers-db'
import { evaluateActivation } from '@/lib/enrollment/activation'
import { loadActivationContext } from '@/lib/enrollment/context'
import { claimIdempotencyKey, completeIdempotentOperation, releaseIdempotencyKey } from '@/lib/enrollment/idempotency'
import { errorEnvelope, statusFor, redactProviderError } from '@/lib/enrollment/errors'
import { findPriceIdByLookupKey, createTrialingSubscription } from '@/lib/billing/stripe'
import { BOT_PLANS } from '@/lib/billing/plans'
import { TRIAL_ELIGIBLE_DAYS } from '@/lib/enrollment/trading-days'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const OPERATION = 'activate'

/**
 * POST /api/v1/activations — activate trading + start the trial (spec §3 ACT-01, §6).
 *
 * This is THE transaction the whole spec builds toward, and it has three properties
 * that are not optional:
 *
 *  ATOMIC — "On success, atomically create activation, set trading active and start
 *  trial counter." Partial success is the worst failure available here: trading live
 *  with no trial record, or a trial burning with no authority to trade. §11 requires
 *  "Activation partially fails → rollback activation/trial; no orders; safe retry".
 *
 *  IDEMPOTENT — a double-clicked Activate, or a client retry after a timeout where the
 *  first request actually succeeded, must produce ONE activation, one subscription, one
 *  trial (§12 "Double click/retry").
 *
 *  RE-CHECKED AT THE LAST MOMENT — §4 re-checks legal versions, payment method,
 *  brokerage token, account eligibility, agent rules and kill-switch. Everything below
 *  is re-read fresh; NOTHING is trusted from the preview except the hash, which is what
 *  proves the customer consented to this exact state.
 */
export async function POST(req: NextRequest) {
  const session = await getCustomerSession()
  if (!session.customerId) {
    const e = errorEnvelope('UNAUTHORIZED', 'Please sign in to continue.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  if (!isCustomersDbConfigured()) {
    const e = errorEnvelope('NOT_CONFIGURED', 'Activation is temporarily unavailable.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }

  const body = (await req.json().catch(() => ({}))) as {
    config_id?: unknown
    preview_hash?: unknown
    risk_acknowledged?: unknown
    authorization_acknowledged?: unknown
  }

  const idemKey = req.headers.get('idempotency-key') ?? ''
  if (!idemKey) {
    const e = errorEnvelope('VALIDATION_FAILED', 'Missing idempotency key.', { field: 'Idempotency-Key' })
    return NextResponse.json(e, { status: statusFor(e.code) })
  }

  // Claimed BEFORE any provider call, so a duplicate never reaches Stripe at all.
  const claim = await claimIdempotencyKey({ key: idemKey, userId: session.customerId, operation: OPERATION })
  if (!claim.claimed) {
    if (claim.response) return NextResponse.json(claim.response)
    // The first call is still in flight. A 409 — never a second execution.
    const e = errorEnvelope('STATE_CONFLICT', 'That request is already being processed.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }

  try {
    // ── Re-read every input fresh (§4), through the SAME loader the preview used ──
    const ctx = await loadActivationContext(session.customerId, String(body.config_id ?? ''))
    if (!ctx) {
      await releaseIdempotencyKey({ key: idemKey, operation: OPERATION })
      const e = errorEnvelope('FORBIDDEN', 'That configuration is not available.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }
    const { config, snapshot, hash: currentHash } = ctx

    const decision = evaluateActivation({
      ...ctx.inputs,
      riskAcknowledged: body.risk_acknowledged === true,
      authorizationAcknowledged: body.authorization_acknowledged === true,
      previewCurrent: String(body.preview_hash ?? '') === currentHash,
    })

    if (!decision.ok) {
      // Nothing durable happened — free the key so a retry is possible after fixing.
      await releaseIdempotencyKey({ key: idemKey, operation: OPERATION })
      const e = errorEnvelope('ACTIVATION_BLOCKED', 'Trading cannot be activated yet.')
      return NextResponse.json(
        { ...e, blockers: decision.blockers, current_preview_hash: currentHash },
        { status: statusFor(e.code) },
      )
    }

    const plan = BOT_PLANS[config.agent_code as 'spark' | 'flame']
    const priceId = plan ? await findPriceIdByLookupKey(plan.lookupKey) : null
    if (!priceId || !ctx.stripeCustomerId) {
      await releaseIdempotencyKey({ key: idemKey, operation: OPERATION })
      const e = errorEnvelope('NOT_CONFIGURED', 'Billing is not fully configured yet.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    // Stripe FIRST: it is the only step that cannot be rolled back, so if it throws
    // nothing local has been written and the released key allows a clean retry.
    const stripeSub = await createTrialingSubscription({
      customerId: ctx.stripeCustomerId,
      priceId,
      userId: session.customerId,
      bot: config.agent_code,
    })

    let activationId = ''
    await customerTransaction(async (run) => {
      const act = (await run(
        `INSERT INTO activations
           (user_id, config_id, status, preview_hash, risk_ack_at, authorization_at, activated_at)
         VALUES ($1, $2, 'active', $3, now(), now(), now())
         RETURNING id`,
        [session.customerId, config.id, currentHash],
      )) as unknown as Array<{ id: string }>
      activationId = act?.[0]?.id ?? ''

      // The ONE place a trial may be opened (§7) — and only from not_started, so a
      // second activation can never hand out a second free run.
      await run(
        `INSERT INTO trials (user_id, agent_code, activation_id, status, started_at, eligible_days_used)
         VALUES ($1, $2, $3, 'active', now(), 0)
         ON CONFLICT (user_id, agent_code) DO UPDATE
            SET status = 'active', started_at = now(),
                activation_id = EXCLUDED.activation_id, updated_at = now()
          WHERE trials.status = 'not_started'`,
        [session.customerId, config.agent_code, activationId],
      )

      await run(
        `INSERT INTO customer_bot_subscriptions
           (user_id, bot, status, stripe_subscription_id, price_lookup_key, updated_at)
         VALUES ($1, $2, 'trialing', $3, $4, now())
         ON CONFLICT (user_id, bot) DO UPDATE
            SET status = 'trialing',
                stripe_subscription_id = EXCLUDED.stripe_subscription_id,
                updated_at = now()`,
        [session.customerId, config.agent_code, stripeSub.id, plan.lookupKey],
      )
    })

    const response = {
      ok: true,
      activation_id: activationId,
      agent: config.agent_code,
      account_mask: snapshot.accountMask,
      trial: { status: 'active', eligible_days_used: 0, eligible_days_total: TRIAL_ELIGIBLE_DAYS },
    }
    await completeIdempotentOperation({ key: idemKey, operation: OPERATION, response })
    return NextResponse.json(response)
  } catch (e) {
    await releaseIdempotencyKey({ key: idemKey, operation: OPERATION }).catch(() => {})
    const env = redactProviderError('v1/activations', e, 'INTERNAL', 'Activation could not be completed. Please try again.')
    return NextResponse.json(env, { status: statusFor(env.code) })
  }
}
