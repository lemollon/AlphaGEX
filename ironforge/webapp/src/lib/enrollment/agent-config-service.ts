import { customerQuery } from '@/lib/customers-db'
import { validateAgentConfig, isConfigurableAgent, RULE_VERSION, AGENT_RULE_SCHEMA } from './agent-rules'
import type { ErrorCode } from './errors'

/**
 * Shared core of "create a DRAFT agent configuration" (spec §3 AGENT-01).
 *
 * Extracted from POST /api/v1/agent-configs (10/5 reorder) so a SECOND caller — the
 * web order's PUT .../broker-account, which now mints the config the moment the
 * brokerage account is chosen, since AGENT-01 no longer has its own screen between
 * broker and billing — goes through IDENTICAL validation as the original AGENT-01
 * screen (still used as-is by the app order and by the web's resume fallback). Two
 * code paths producing agent_configs rows under different rules is how a customer
 * ends up with a "valid" config the real rule schema would have rejected.
 *
 * Always submits config: {} (server defaults) — the only input AGENT-01's client ever
 * sent in practice (the rule schema has nothing the funnel lets a customer type in at
 * this screen), so dropping the pass-through parameter loses no real capability.
 *
 * Never activates anything — same as the route it was extracted from.
 */
export interface AgentConfigDraft {
  id: string
  agent_code: string
  rule_version: string
  status: string
  schema: unknown
  limits: { max_deployment_cents: number | null; buying_power_cents: number | null }
  violations: unknown
  warnings: unknown
}

export type AgentConfigDraftResult =
  | ({ ok: true } & AgentConfigDraft)
  | { ok: false; code: ErrorCode; message: string; field?: string }

export async function createAgentConfigDraft(opts: {
  userId: string
  agentCode: string
  brokerAccountId: string
}): Promise<AgentConfigDraftResult> {
  if (!isConfigurableAgent(opts.agentCode)) {
    return { ok: false, code: 'VALIDATION_FAILED', message: 'Choose Spark, Flame or Ember.', field: 'agent_code' }
  }

  // Ownership via the connection join — an account id alone is never authority (§8).
  const acct = (await customerQuery<{
    id: string; eligibility: string; ineligible_reason: string | null; buying_power_cents: string | null
  }>(
    `SELECT ba.id, ba.eligibility, ba.ineligible_reason, ba.buying_power_cents
       FROM broker_accounts ba
       JOIN brokerage_connections bc ON bc.id = ba.connection_id
      WHERE ba.id = $1 AND bc.user_id = $2 LIMIT 1`,
    [opts.brokerAccountId, opts.userId],
  ))[0]

  if (!acct) {
    return { ok: false, code: 'FORBIDDEN', message: 'That account is not available.' }
  }
  if (acct.eligibility !== 'eligible') {
    return {
      ok: false,
      code: 'BROKER_ACCOUNT_INELIGIBLE',
      message: acct.ineligible_reason || 'This account is not eligible for automated options trading.',
      field: 'broker_account_id',
    }
  }

  // From the ACCOUNT row, captured at brokerage sync. Reading it from a prior config
  // would make the very first configuration impossible — there is none to read.
  const bp = acct.buying_power_cents == null ? null : Number(acct.buying_power_cents)
  const result = validateAgentConfig({ agentCode: opts.agentCode, input: {}, buyingPowerCents: bp })

  // Persisted as a DRAFT even when invalid, so a customer can leave and come back to
  // a half-finished setup — the funnel is resumable (§3 DONE-01).
  const rows = await customerQuery<{ id: string }>(
    `INSERT INTO agent_configs
       (user_id, broker_account_id, agent_code, rule_version, config_json, status, validated_at)
     VALUES ($1, $2, $3, $4, $5, $6, CASE WHEN $6 = 'valid' THEN now() ELSE NULL END)
     RETURNING id`,
    [
      opts.userId,
      opts.brokerAccountId,
      opts.agentCode,
      RULE_VERSION,
      JSON.stringify({
        ...result.computed.config,
        max_deployment_cents: result.computed.maxDeploymentCents,
        buying_power_cents: result.computed.buyingPowerCents,
      }),
      result.valid ? 'valid' : 'draft',
    ],
  )

  return {
    ok: true,
    id: rows[0].id,
    agent_code: opts.agentCode,
    rule_version: RULE_VERSION,
    status: result.valid ? 'valid' : 'draft',
    schema: AGENT_RULE_SCHEMA[opts.agentCode],
    limits: { max_deployment_cents: result.computed.maxDeploymentCents, buying_power_cents: result.computed.buyingPowerCents },
    violations: result.violations,
    warnings: result.warnings,
  }
}
