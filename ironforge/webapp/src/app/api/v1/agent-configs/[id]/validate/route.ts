import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import { validateAgentConfig, RULE_VERSION } from '@/lib/enrollment/agent-rules'
import { errorEnvelope, statusFor, redactProviderError } from '@/lib/enrollment/errors'
import { isUuid } from '@/lib/enrollment/ids'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * POST /api/v1/agent-configs/{id}/validate — "Returns violations/warnings" (§6).
 *
 * Re-validates against the CURRENT rule version and the CURRENT account value, then
 * writes the resulting status. Two things this catches that a create-time check cannot:
 *
 *  - A RULE VERSION BUMP. A config validated under 1.0 is not valid under 1.1; it must
 *    come back through here rather than being trusted because it was once fine.
 *  - MOVED BUYING POWER. Limits are recomputed from the account's current value, so a
 *    config that was sized against a larger balance is re-sized or rejected before it
 *    can reach activation.
 *
 * A config can only ever become `valid` HERE. Activation reads that status and does not
 * re-derive it, which keeps one place responsible for the answer.
 */
export async function POST(_req: NextRequest, { params }: { params: { id: string } }) {
  const identity = await getCustomerIdentity()
  // Cookie OR mobile bearer. Shape preserved so the checks below read unchanged.
  const session = { customerId: identity?.customerId ?? null }
  if (!session.customerId) {
    const e = errorEnvelope('UNAUTHORIZED', 'Please sign in to continue.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  if (!isCustomersDbConfigured()) {
    const e = errorEnvelope('NOT_CONFIGURED', 'Setup is temporarily unavailable.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }

  try {
    // Malformed ids raise on the UUID cast rather than returning no rows; answered the
    // same way as an id that is not the caller's.
    if (!isUuid(params.id)) {
      const e = errorEnvelope('FORBIDDEN', 'That configuration is not available.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    const cfg = (await customerQuery<{
      id: string; agent_code: string; rule_version: string
      broker_account_id: string | null; config_json: Record<string, unknown>
    }>(
      `SELECT id, agent_code, rule_version, broker_account_id, config_json
         FROM agent_configs WHERE id = $1 AND user_id = $2 LIMIT 1`,
      [params.id, session.customerId],
    ))[0]

    if (!cfg) {
      const e = errorEnvelope('FORBIDDEN', 'That configuration is not available.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    const acct = cfg.broker_account_id
      ? (await customerQuery<{
          id: string; eligibility: string; ineligible_reason: string | null; buying_power_cents: string | null
        }>(
          `SELECT ba.id, ba.eligibility, ba.ineligible_reason, ba.buying_power_cents
             FROM broker_accounts ba
             JOIN brokerage_connections bc ON bc.id = ba.connection_id
            WHERE ba.id = $1 AND bc.user_id = $2 LIMIT 1`,
          [cfg.broker_account_id, session.customerId],
        ))[0]
      : undefined

    // The account can have become ineligible since the draft was made — options level
    // downgraded, account restricted, balance drained.
    if (!acct || acct.eligibility !== 'eligible') {
      await customerExecute(
        `UPDATE agent_configs SET status = 'draft', validated_at = NULL, updated_at = now() WHERE id = $1`,
        [cfg.id],
      )
      const e = errorEnvelope(
        'BROKER_ACCOUNT_INELIGIBLE',
        acct?.ineligible_reason || 'This account is not eligible for automated options trading.',
        { field: 'broker_account_id' },
      )
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    const result = validateAgentConfig({
      agentCode: cfg.agent_code,
      input: cfg.config_json ?? {},
      buyingPowerCents: acct.buying_power_cents == null ? null : Number(acct.buying_power_cents),
    })

    await customerExecute(
      `UPDATE agent_configs
          SET status = $2,
              rule_version = $3,
              config_json = $4,
              validated_at = CASE WHEN $2 = 'valid' THEN now() ELSE NULL END,
              updated_at = now()
        WHERE id = $1`,
      [
        cfg.id,
        result.valid ? 'valid' : 'draft',
        RULE_VERSION,
        JSON.stringify({
          ...result.computed.config,
          max_deployment_cents: result.computed.maxDeploymentCents,
          buying_power_cents: result.computed.buyingPowerCents,
        }),
      ],
    )

    return NextResponse.json({
      id: cfg.id,
      status: result.valid ? 'valid' : 'draft',
      rule_version: RULE_VERSION,
      // Surfaced so a UI can show the version moved under the customer.
      revalidated_from: cfg.rule_version,
      limits: {
        max_deployment_cents: result.computed.maxDeploymentCents,
        buying_power_cents: result.computed.buyingPowerCents,
      },
      violations: result.violations,
      warnings: result.warnings,
    })
  } catch (e) {
    const env = redactProviderError('v1/validate', e, 'INTERNAL', 'Could not check your settings. Please try again.')
    return NextResponse.json(env, { status: statusFor(env.code) })
  }
}
