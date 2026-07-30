/**
 * Agent configuration rules (Enrollment spec §3 AGENT-01, AGENT-02).
 *
 * "Users may adjust only parameters exposed by the approved rule schema" and "Validate
 * server-side against agent version, account value and platform limits."
 *
 * The schema is an ALLOWLIST, not a set of checks on arbitrary input. Anything not
 * named here is ignored rather than rejected, so a client that invents a field cannot
 * smuggle it into config_json and have some later reader honour it.
 *
 * `rule_version` is stamped on every config. When these bounds change the version moves,
 * and every previously-valid config referencing the old version becomes `stale` — which
 * is what makes "any account or agent change invalidates the activation review" (§3)
 * enforceable rather than aspirational.
 *
 * Pure: no I/O, no clock.
 */

/** Bump when any bound below changes. Existing configs on an older version go stale. */
export const RULE_VERSION = '1.1'

export interface RuleField {
  key: string
  label: string
  min: number
  max: number
  default: number
  unit: 'percent'
}

/**
 * Deployment ceiling as a percentage of option buying power.
 *
 * Bounds mirror the platform's own sizing clamp (half-Kelly, 10%–85%) — a customer
 * must not be able to configure something the scanner would refuse to execute, because
 * that produces a bot that looks configured and never trades.
 */
const MAX_DEPLOYMENT: RuleField = {
  key: 'max_deployment_pct',
  label: 'Maximum capital deployed per trade',
  min: 10,
  max: 85,
  // 20% is the launch default Leron approved 7/30, matching the approved ACT-01
  // screen. Was 50 under rule 1.0; the version bump stales any config on the old
  // default so nothing activates against a number the customer never reviewed.
  default: 20,
  unit: 'percent',
}

export const AGENT_RULE_SCHEMA: Record<string, RuleField[]> = {
  spark: [MAX_DEPLOYMENT],
  flame: [MAX_DEPLOYMENT],
}

export function isConfigurableAgent(code: string): boolean {
  return Object.prototype.hasOwnProperty.call(AGENT_RULE_SCHEMA, code)
}

export interface Violation {
  field: string
  message: string
}

export interface ValidationResult {
  valid: boolean
  violations: Violation[]
  warnings: string[]
  /** Server-computed, never taken from the client. */
  computed: {
    maxDeploymentCents: number
    buyingPowerCents: number
    /** The sanitised config to persist — allowlisted keys only. */
    config: Record<string, number>
  }
}

/**
 * Validate a draft against the schema and the CURRENT account value.
 *
 * Limits are computed here, server-side, from live buying power: "Returns calculated
 * limits" (§6). A client-supplied limit is never trusted, and because the computed
 * figure lands in the activation snapshot, a buying-power move between configuring and
 * activating changes the preview hash and forces a fresh confirmation (§4).
 */
export function validateAgentConfig(opts: {
  agentCode: string
  input: Record<string, unknown>
  buyingPowerCents: number | null
}): ValidationResult {
  const violations: Violation[] = []
  const warnings: string[] = []
  const config: Record<string, number> = {}

  const schema = AGENT_RULE_SCHEMA[opts.agentCode]
  if (!schema) {
    return {
      valid: false,
      violations: [{ field: 'agent_code', message: 'That strategy is not available.' }],
      warnings,
      computed: { maxDeploymentCents: 0, buyingPowerCents: 0, config },
    }
  }

  for (const f of schema) {
    const raw = opts.input[f.key]
    // Absent → the approved default, not a failure. A customer who changes nothing
    // should get a valid config.
    const value = raw == null || raw === '' ? f.default : Number(raw)
    if (!Number.isFinite(value)) {
      violations.push({ field: f.key, message: `${f.label} must be a number.` })
      continue
    }
    if (value < f.min || value > f.max) {
      violations.push({ field: f.key, message: `${f.label} must be between ${f.min}% and ${f.max}%.` })
    }
    // RETAINED EVEN WHEN OUT OF RANGE — deliberately.
    //
    // Dropping a rejected value would make it ABSENT on the next read, and absent means
    // "use the default", so simply re-validating an invalid draft would turn it valid
    // without the customer changing anything.
    // /v1/agent-configs/{id}/validate feeds the persisted config straight back in, so
    // that path was reachable. Keeping the offending number makes re-validation
    // reproduce the same violation, which is the only honest answer.
    //
    // Not a hole: the value is still allowlisted (an unknown key never reaches here),
    // the config stays `draft`, and no limit is computed from it below.
    config[f.key] = value
  }

  // Unknown buying power is not a validation error — it is a REASON THIS CANNOT BE
  // VALIDATED YET. Treated as zero so no limit is computed from a guess.
  const bp = opts.buyingPowerCents ?? 0
  if (opts.buyingPowerCents == null) {
    violations.push({
      field: 'broker_account_id',
      message: 'We could not read this account’s buying power. Reconnect your brokerage and try again.',
    })
  }

  const pct = config[MAX_DEPLOYMENT.key] ?? MAX_DEPLOYMENT.default
  // A limit derived from a rejected percentage would be a number that means nothing —
  // and it is the number the activation snapshot would hash. Invalid configs carry no
  // limit at all.
  const maxDeploymentCents = violations.length === 0 ? Math.floor((bp * pct) / 100) : 0

  if (violations.length === 0 && opts.buyingPowerCents != null && maxDeploymentCents < 20_000) {
    // $200 is the scanner's own floor for opening a position.
    warnings.push('At this account size the strategy may not find a position it can open.')
  }

  return {
    valid: violations.length === 0,
    violations,
    warnings,
    computed: { maxDeploymentCents, buyingPowerCents: bp, config },
  }
}
