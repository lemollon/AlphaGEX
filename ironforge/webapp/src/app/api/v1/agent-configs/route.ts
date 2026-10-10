import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured } from '@/lib/customers-db'
import { isConfigurableAgent } from '@/lib/enrollment/agent-rules'
import { createAgentConfigDraft } from '@/lib/enrollment/agent-config-service'
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
    const body = (await req.json().catch(() => ({}))) as {
      agent_code?: unknown; broker_account_id?: unknown; config?: unknown
    }
    const agentCode = String(body.agent_code ?? '')
    const brokerAccountId = String(body.broker_account_id ?? '')

    if (!isConfigurableAgent(agentCode)) {
      const e = errorEnvelope('VALIDATION_FAILED', 'Choose Spark, Flame or Ember.', { field: 'agent_code' })
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    // Malformed ids raise on the UUID cast rather than returning no rows.
    if (!isUuid(brokerAccountId)) {
      const e = errorEnvelope('FORBIDDEN', 'That account is not available.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    // config: {} — this screen's rule schema has nothing the client sends; the real
    // inputs are the account's own buying power, read server-side inside the shared
    // draft creator below.
    const draft = await createAgentConfigDraft({ userId: session.customerId, agentCode, brokerAccountId })
    if (!draft.ok) {
      const e = errorEnvelope(draft.code, draft.message, draft.field ? { field: draft.field } : undefined)
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    return NextResponse.json({
      id: draft.id,
      agent_code: draft.agent_code,
      rule_version: draft.rule_version,
      status: draft.status,
      schema: draft.schema,
      limits: draft.limits,
      violations: draft.violations,
      warnings: draft.warnings,
    })
  } catch (e) {
    const env = redactProviderError('v1/agent-configs', e, 'INTERNAL', 'Could not save your settings. Please try again.')
    return NextResponse.json(env, { status: statusFor(env.code) })
  }
}
