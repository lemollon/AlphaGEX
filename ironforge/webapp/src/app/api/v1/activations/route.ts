import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured, customerQuery, customerTransaction } from '@/lib/customers-db'
import { evaluateActivation } from '@/lib/enrollment/activation'
import { previewHash, type ActivationSnapshot } from '@/lib/enrollment/preview'
import { staleDocumentCodes } from '@/lib/enrollment/legal'
import { acceptedVersionsFor } from '@/lib/enrollment/service'
import { claimIdempotencyKey, completeIdempotentOperation, releaseIdempotencyKey } from '@/lib/enrollment/idempotency'
import { errorEnvelope, statusFor, redactProviderError } from '@/lib/enrollment/errors'
import { getProductionPauseState } from '@/lib/tradier'
import { findPriceIdByLookupKey, createTrialingSubscription, hasUsablePaymentMethod } from '@/lib/billing/stripe'
import { BOT_PLANS } from '@/lib/billing/plans'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const OPERATION = 'activate'

interface ConfigRow {
  id: string
  agent_code: string
  rule_version: string
  status: string
  broker_account_id: string | null
  config_json: Record<string, unknown>
}

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
    const configId = String(body.config_id ?? '')
    const config = (await customerQuery<ConfigRow>(
      `SELECT id, agent_code, rule_version, status, broker_account_id, config_json
         FROM agent_configs WHERE id = $1 AND user_id = $2 LIMIT 1`,
      [configId, session.customerId],
    ))[0]

    if (!config) {
      await releaseIdempotencyKey({ key: idemKey, operation: OPERATION })
      const e = errorEnvelope('FORBIDDEN', 'That configuration is not available.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    // ── Re-read every input fresh (§4) ─────────────────────────────────────────
    const acct = config.broker_account_id
      ? (await customerQuery<{
          id: string; eligibility: string; ineligible_reason: string | null; display_mask: string
        }>(
          `SELECT ba.id, ba.eligibility, ba.ineligible_reason, ba.display_mask
             FROM broker_accounts ba
             JOIN brokerage_connections bc ON bc.id = ba.connection_id
            WHERE ba.id = $1 AND bc.user_id = $2 LIMIT 1`,
          [config.broker_account_id, session.customerId],
        ))[0]
      : undefined

    const conn = (await customerQuery<{ status: string }>(
      `SELECT status FROM brokerage_connections WHERE user_id = $1 ORDER BY updated_at DESC LIMIT 1`,
      [session.customerId],
    ))[0]

    const sub = (await customerQuery<{ status: string }>(
      `SELECT status FROM customer_bot_subscriptions WHERE user_id = $1 AND bot = $2 LIMIT 1`,
      [session.customerId, config.agent_code],
    ))[0]

    const user = (await customerQuery<{ stripe_customer_id: string | null }>(
      `SELECT stripe_customer_id FROM users WHERE id = $1 LIMIT 1`,
      [session.customerId],
    ))[0]

    // Kill-switch read fails CLOSED: an unreadable pause state counts as engaged.
    const pause = await getProductionPauseState(config.agent_code).catch(() => ({ paused: true }))
    const accepted = await acceptedVersionsFor(session.customerId)
    const paymentOk = user?.stripe_customer_id ? await hasUsablePaymentMethod(user.stripe_customer_id) : false

    const snapshot: ActivationSnapshot = {
      userId: session.customerId,
      brokerAccountId: acct?.id ?? '',
      accountMask: acct?.display_mask ?? '',
      agentCode: config.agent_code,
      ruleVersion: config.rule_version,
      maxDeploymentCents: Number(config.config_json?.max_deployment_cents ?? 0),
      buyingPowerCents: Number(config.config_json?.buying_power_cents ?? 0),
      legalVersions: accepted.map((a) => `${a.code}@${a.version}`),
    }
    const currentHash = previewHash(snapshot)

    const decision = evaluateActivation({
      membership: (sub?.status as never) ?? 'pending',
      paymentMethodValid: paymentOk,
      staleLegalDocuments: staleDocumentCodes(config.agent_code, accepted),
      brokerage: conn?.status === 'active' ? 'connected' : 'not_connected',
      accountEligible: acct?.eligibility === 'eligible',
      accountIneligibleReason: acct?.ineligible_reason ?? undefined,
      agentConfig: config.status as never,
      killSwitchEngaged: pause.paused === true,
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
    if (!priceId || !user?.stripe_customer_id) {
      await releaseIdempotencyKey({ key: idemKey, operation: OPERATION })
      const e = errorEnvelope('NOT_CONFIGURED', 'Billing is not fully configured yet.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    // Stripe FIRST: it is the only step that cannot be rolled back, so if it throws
    // nothing local has been written and the released key allows a clean retry.
    const stripeSub = await createTrialingSubscription({
      customerId: user.stripe_customer_id,
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
      trial: { status: 'active', eligible_days_used: 0, eligible_days_total: 5 },
    }
    await completeIdempotentOperation({ key: idemKey, operation: OPERATION, response })
    return NextResponse.json(response)
  } catch (e) {
    await releaseIdempotencyKey({ key: idemKey, operation: OPERATION }).catch(() => {})
    const env = redactProviderError('v1/activations', e, 'INTERNAL', 'Activation could not be completed. Please try again.')
    return NextResponse.json(env, { status: statusFor(env.code) })
  }
}
