import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'
import { validateAgentConfig, isConfigurableAgent, RULE_VERSION, AGENT_RULE_SCHEMA } from '@/lib/enrollment/agent-rules'
import { errorEnvelope, statusFor, redactProviderError } from '@/lib/enrollment/errors'
import { isUuid } from '@/lib/enrollment/ids'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * POST /api/v1/agent-configs — create a DRAFT configuration (spec §3 AGENT-01, §6).
 *
 * "Selecting an agent creates a draft configuration; it does not activate trading."
 * That separation is the point: choosing Spark is not authority to trade Spark, and
 * this route can never produce anything but a draft.
 *
 * "Returns calculated limits" — computed server-side from live buying power, never
 * from anything the client sends.
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
    const body = (await req.json().catch(() => ({}))) as {
      agent_code?: unknown; broker_account_id?: unknown; config?: unknown
    }
    const agentCode = String(body.agent_code ?? '')
    const brokerAccountId = String(body.broker_account_id ?? '')

    if (!isConfigurableAgent(agentCode)) {
      const e = errorEnvelope('VALIDATION_FAILED', 'Choose Spark or Flame.', { field: 'agent_code' })
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    // Malformed ids raise on the UUID cast rather than returning no rows.
    if (!isUuid(brokerAccountId)) {
      const e = errorEnvelope('FORBIDDEN', 'That account is not available.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    // Ownership via the connection join — an account id alone is never authority (§8).
    const acct = (await customerQuery<{
      id: string; eligibility: string; ineligible_reason: string | null; buying_power_cents: string | null
    }>(
      `SELECT ba.id, ba.eligibility, ba.ineligible_reason, ba.buying_power_cents
         FROM broker_accounts ba
         JOIN brokerage_connections bc ON bc.id = ba.connection_id
        WHERE ba.id = $1 AND bc.user_id = $2 LIMIT 1`,
      [brokerAccountId, session.customerId],
    ))[0]

    if (!acct) {
      const e = errorEnvelope('FORBIDDEN', 'That account is not available.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }
    if (acct.eligibility !== 'eligible') {
      const e = errorEnvelope(
        'BROKER_ACCOUNT_INELIGIBLE',
        acct.ineligible_reason || 'This account is not eligible for automated options trading.',
        { field: 'broker_account_id' },
      )
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    // From the ACCOUNT row, captured at brokerage sync. Reading it from a prior config
    // would make the very first configuration impossible — there is none to read.
    const bp = acct.buying_power_cents == null ? null : Number(acct.buying_power_cents)
    const result = validateAgentConfig({
      agentCode,
      input: (body.config as Record<string, unknown>) ?? {},
      buyingPowerCents: bp,
    })

    // Persisted as a DRAFT even when invalid, so a customer can leave and come back to
    // a half-finished setup — the funnel is resumable (§3 DONE-01).
    const rows = await customerQuery<{ id: string }>(
      `INSERT INTO agent_configs
         (user_id, broker_account_id, agent_code, rule_version, config_json, status, validated_at)
       VALUES ($1, $2, $3, $4, $5, $6, CASE WHEN $6 = 'valid' THEN now() ELSE NULL END)
       RETURNING id`,
      [
        session.customerId,
        brokerAccountId,
        agentCode,
        RULE_VERSION,
        JSON.stringify({
          ...result.computed.config,
          max_deployment_cents: result.computed.maxDeploymentCents,
          buying_power_cents: result.computed.buyingPowerCents,
        }),
        result.valid ? 'valid' : 'draft',
      ],
    )

    return NextResponse.json({
      id: rows[0].id,
      agent_code: agentCode,
      rule_version: RULE_VERSION,
      status: result.valid ? 'valid' : 'draft',
      schema: AGENT_RULE_SCHEMA[agentCode],
      limits: {
        max_deployment_cents: result.computed.maxDeploymentCents,
        buying_power_cents: result.computed.buyingPowerCents,
      },
      violations: result.violations,
      warnings: result.warnings,
    })
  } catch (e) {
    const env = redactProviderError('v1/agent-configs', e, 'INTERNAL', 'Could not save your settings. Please try again.')
    return NextResponse.json(env, { status: statusFor(env.code) })
  }
}
