import { describe, it, expect } from 'vitest'
import {
  validateAgentConfig,
  isConfigurableAgent,
  AGENT_RULE_SCHEMA,
  RULE_VERSION,
} from '../agent-rules'

const BP = 1_000_000 // $10,000 in cents

describe('isConfigurableAgent', () => {
  it('accepts only the two shipped products', () => {
    expect(isConfigurableAgent('spark')).toBe(true)
    expect(isConfigurableAgent('flame')).toBe(true)
    // INFERNO is an internal bot, not a product a customer may configure.
    expect(isConfigurableAgent('inferno')).toBe(false)
    expect(isConfigurableAgent('')).toBe(false)
  })

  it('is not fooled by inherited Object properties', () => {
    // hasOwnProperty, not `in` — otherwise 'constructor' and 'toString' pass.
    expect(isConfigurableAgent('constructor')).toBe(false)
    expect(isConfigurableAgent('toString')).toBe(false)
  })
})

describe('validateAgentConfig — allowlist', () => {
  it('drops unknown fields instead of persisting them', () => {
    const r = validateAgentConfig({
      agentCode: 'spark',
      input: { max_deployment_pct: 50, stop_loss_pct: 5, __proto__: 'x', enabled: true },
      buyingPowerCents: BP,
    })
    expect(r.valid).toBe(true)
    // Only the schema key survives — a client cannot smuggle a field into config_json.
    expect(Object.keys(r.computed.config)).toEqual(['max_deployment_pct'])
  })

  it('rejects an unknown agent without computing limits', () => {
    const r = validateAgentConfig({ agentCode: 'inferno', input: {}, buyingPowerCents: BP })
    expect(r.valid).toBe(false)
    expect(r.violations[0].field).toBe('agent_code')
    expect(r.computed.maxDeploymentCents).toBe(0)
  })
})

describe('validateAgentConfig — bounds', () => {
  it('applies the default when the field is absent or blank', () => {
    for (const input of [{}, { max_deployment_pct: '' }, { max_deployment_pct: null }]) {
      const r = validateAgentConfig({ agentCode: 'spark', input, buyingPowerCents: BP })
      expect(r.valid).toBe(true)
      expect(r.computed.config.max_deployment_pct).toBe(50)
    }
  })

  it('accepts the inclusive endpoints', () => {
    for (const pct of [10, 85]) {
      const r = validateAgentConfig({
        agentCode: 'flame',
        input: { max_deployment_pct: pct },
        buyingPowerCents: BP,
      })
      expect(r.valid).toBe(true)
    }
  })

  it('rejects outside the platform sizing clamp', () => {
    for (const pct of [9.9, 0, 85.1, 100, -50]) {
      const r = validateAgentConfig({
        agentCode: 'flame',
        input: { max_deployment_pct: pct },
        buyingPowerCents: BP,
      })
      expect(r.valid).toBe(false)
      expect(r.violations[0].field).toBe('max_deployment_pct')
    }
  })

  it('rejects non-numeric input rather than coercing it', () => {
    for (const bad of ['fifty', {}, [1, 2], NaN, Infinity]) {
      const r = validateAgentConfig({
        agentCode: 'spark',
        input: { max_deployment_pct: bad },
        buyingPowerCents: BP,
      })
      expect(r.valid).toBe(false)
    }
  })
})

describe('validateAgentConfig — computed limits', () => {
  it('computes the ceiling server-side from buying power', () => {
    const r = validateAgentConfig({
      agentCode: 'spark',
      input: { max_deployment_pct: 25 },
      buyingPowerCents: BP,
    })
    expect(r.computed.maxDeploymentCents).toBe(250_000) // $2,500
    expect(r.computed.buyingPowerCents).toBe(BP)
  })

  it('ignores a client-supplied limit entirely', () => {
    const r = validateAgentConfig({
      agentCode: 'spark',
      input: { max_deployment_pct: 10, max_deployment_cents: 99_999_999 },
      buyingPowerCents: BP,
    })
    expect(r.computed.maxDeploymentCents).toBe(100_000)
  })

  it('floors rather than rounding up — never authorize a cent more than earned', () => {
    const r = validateAgentConfig({
      agentCode: 'spark',
      input: { max_deployment_pct: 33 },
      buyingPowerCents: 101, // 33.33 cents
    })
    expect(r.computed.maxDeploymentCents).toBe(33)
  })

  it('treats unknown buying power as a blocker, not as zero-and-valid', () => {
    const r = validateAgentConfig({ agentCode: 'spark', input: {}, buyingPowerCents: null })
    expect(r.valid).toBe(false)
    expect(r.violations.some((v) => v.field === 'broker_account_id')).toBe(true)
    // No limit is invented from a guess.
    expect(r.computed.maxDeploymentCents).toBe(0)
  })

  it('warns — but stays valid — when the account is too small to open a position', () => {
    const r = validateAgentConfig({
      agentCode: 'flame',
      input: { max_deployment_pct: 10 },
      buyingPowerCents: 100_000, // $1,000 -> $100 deployable, under the $200 floor
    })
    expect(r.valid).toBe(true)
    expect(r.warnings).toHaveLength(1)
  })

  it('does not warn about size when buying power is simply unknown', () => {
    const r = validateAgentConfig({ agentCode: 'flame', input: {}, buyingPowerCents: null })
    expect(r.warnings).toHaveLength(0)
  })
})

describe('rule version', () => {
  it('is a non-empty string stamped on every config', () => {
    expect(RULE_VERSION).toMatch(/^\d+\.\d+$/)
  })

  it('covers every configurable agent with at least one field', () => {
    for (const code of Object.keys(AGENT_RULE_SCHEMA)) {
      expect(AGENT_RULE_SCHEMA[code].length).toBeGreaterThan(0)
      for (const f of AGENT_RULE_SCHEMA[code]) {
        // A default outside its own bounds would make an untouched form invalid.
        expect(f.default).toBeGreaterThanOrEqual(f.min)
        expect(f.default).toBeLessThanOrEqual(f.max)
      }
    }
  })
})
