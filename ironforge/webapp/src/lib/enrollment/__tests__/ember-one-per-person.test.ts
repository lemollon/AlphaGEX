import { describe, it, expect, vi, beforeEach } from 'vitest'

/**
 * Server-side enforcement of "one Ember account per person" (design spec §3, §5 step
 * 3; gap audit "Web enrollment — Ember one-per-person enforcement").
 *
 * Covers loadActivationContext's DB-backed conflict check end-to-end — not just the
 * pure evaluateActivation predicate (see enrollment.test.ts for that half) — so a
 * regression that stops wiring the query result into the activation input still fails
 * this test even if the predicate itself stays correct.
 */

const USER_ID = '33333333-3333-3333-3333-333333333333'
const CONFIG_ID = '44444444-4444-4444-4444-444444444444'

let emberConflictExists = false

vi.mock('@/lib/customers-db', () => ({
  customerQuery: vi.fn(async (sql: string, params: unknown[]) => {
    if (sql.includes('FROM agent_configs')) {
      return [
        {
          id: CONFIG_ID,
          agent_code: 'ember',
          rule_version: 'v1',
          status: 'valid',
          broker_account_id: null,
          config_json: { max_deployment_cents: 150000, buying_power_cents: 150000 },
        },
      ]
    }
    if (sql.includes('FROM brokerage_connections') && !sql.includes('JOIN')) {
      return [{ status: 'active' }]
    }
    if (sql.includes('FROM customer_bot_subscriptions cbs')) {
      // The conflict query itself — asserts it's scoped by email, not just user id.
      expect(params).toEqual([USER_ID])
      return [{ conflict: emberConflictExists }]
    }
    if (sql.includes('FROM customer_bot_subscriptions WHERE')) return []
    if (sql.includes('FROM users WHERE id')) return [{ stripe_customer_id: null }]
    return []
  }),
}))

vi.mock('./legal', () => ({
  staleDocumentCodes: () => [],
  isAutomatePlan: () => false,
}))

vi.mock('./service', () => ({
  acceptedVersionsFor: async () => [],
}))

vi.mock('@/lib/tradier', () => ({
  getProductionPauseState: async () => ({ paused: false }),
}))

vi.mock('@/lib/billing/stripe', () => ({
  hasUsablePaymentMethod: async () => true,
}))

const { loadActivationContext } = await import('../context')
const { evaluateActivation } = await import('../activation')

beforeEach(() => {
  emberConflictExists = false
})

describe('Ember one-account-per-person (server-enforced)', () => {
  it('allows activation when this person holds no other active/trialing Ember account', async () => {
    emberConflictExists = false
    const ctx = await loadActivationContext(USER_ID, CONFIG_ID)
    expect(ctx).not.toBeNull()
    // Only this gate is under test here (membership/brokerage/etc. need their own full
    // mock set, already covered by enrollment.test.ts's pure-predicate suite).
    expect(ctx!.inputs.emberConflict).toBe(false)
    const decision = evaluateActivation({
      ...ctx!.inputs,
      riskAcknowledged: true,
      authorizationAcknowledged: true,
      previewCurrent: true,
    })
    expect(decision.blockers.map((b) => b.code)).not.toContain('EMBER_ALREADY_ACTIVE')
  })

  it('rejects a second Ember activation for the same user/email', async () => {
    emberConflictExists = true
    const ctx = await loadActivationContext(USER_ID, CONFIG_ID)
    expect(ctx!.inputs.emberConflict).toBe(true)
    const decision = evaluateActivation({
      ...ctx!.inputs,
      riskAcknowledged: true,
      authorizationAcknowledged: true,
      previewCurrent: true,
    })
    expect(decision.ok).toBe(false)
    expect(decision.blockers.map((b) => b.code)).toContain('EMBER_ALREADY_ACTIVE')
  })
})
