import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

/**
 * Contract tests for the comp-a-membership half of /api/ops/customers.
 *
 * Source-level rather than behavioural because the route reaches two databases and
 * the failure mode here is not logic a mock would exercise — it is a wrong constant
 * or a missing guard. Each assertion below is a bug that shipped or nearly shipped
 * while this was being written.
 */
const SRC = readFileSync(join(__dirname, '..', 'customers', 'route.ts'), 'utf8')

describe('ops/customers membership grants', () => {
  it('writes entitlement to the customers DB, not the bot DB', () => {
    // The whole reason this action exists: `map` writes ironforge_customer_bots and
    // does NOT unlock the app. Granting into the wrong table would look like it
    // worked and leave the customer signed in and locked out.
    const grant = SRC.slice(SRC.indexOf("action === 'grant'"))
    expect(grant).toContain('customerExecute')
    expect(grant).toContain('INSERT INTO customer_bot_subscriptions')
  })

  it('grants a status that actually unlocks the app', () => {
    // LIVE_STATUSES = trialing | active | past_due. Any other string writes a row
    // that reads as a subscription in the table and grants nothing.
    expect(SRC).toMatch(/VALUES \(\$1, \$2, 'active'\)/)
  })

  it('offers the paper strategy, so a demo account need not expose real money', () => {
    expect(SRC).toMatch(/const GRANTABLE = \[[^\]]*'spark2'/)
  })

  it('offers community, which is not in LIVE_BOTS', () => {
    expect(SRC).toMatch(/const GRANTABLE = \[[^\]]*COMMUNITY_KEY/)
  })

  it('refuses to touch a Stripe-billed subscription', () => {
    // Revoking one would cut access while the card keeps being charged.
    expect(SRC).toContain('stripe_owned')
    expect(SRC).toMatch(/stripe_subscription_id !== null/)
  })

  it('leaves stripe_subscription_id NULL so a comp is never mistaken for revenue', () => {
    // Assert on the INSERT's column list, not on the surrounding block — the comment
    // above it names the column, and matching that would pass while the SQL was wrong.
    const cols = /INSERT INTO customer_bot_subscriptions \(([^)]*)\)/.exec(SRC)?.[1]
    expect(cols).toBeDefined()
    expect(cols!.split(',').map((c) => c.trim())).toEqual(['user_id', 'bot', 'status'])
  })

  it('cancels rather than deletes on revoke, keeping the record of the comp', () => {
    expect(SRC).toMatch(/UPDATE customer_bot_subscriptions SET status = 'canceled'/)
    expect(SRC).not.toMatch(/DELETE FROM customer_bot_subscriptions/)
  })

  it('audits both directions', () => {
    expect(SRC).toContain('OPS_MEMBERSHIP_GRANTED')
    expect(SRC).toContain('OPS_MEMBERSHIP_REVOKED')
  })
})
