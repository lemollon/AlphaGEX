import { describe, it, expect, vi, beforeEach } from 'vitest'

/**
 * upsertSubscription is shared by THREE writers (Stripe webhook, Apple verify, Apple
 * server notifications) and is the one place a cross-provider clobber could kill a
 * live entitlement — a stale Apple restore landing after Stripe is the real, current
 * subscription (or the reverse). These tests assert the ownership guard: a write from
 * a DIFFERENT provider than the one currently active/paying is refused, while every
 * same-provider write, and every write onto a row that is not active/paying, proceeds.
 */

let rows: Array<{ provider: string; status: string }> = []
const executed: Array<{ sql: string; params: unknown[] }> = []

vi.mock('@/lib/customers-db', () => ({
  customerQuery: vi.fn(async () => rows),
  customerExecute: vi.fn(async (sql: string, params: unknown[] = []) => {
    executed.push({ sql, params })
    return 1
  }),
}))

const { upsertSubscription } = await import('../membership-sync')

beforeEach(() => {
  rows = []
  executed.length = 0
  vi.clearAllMocks()
})

describe('upsertSubscription — cross-provider ownership guard', () => {
  it('refuses an Apple event that would clobber an active Stripe row', async () => {
    rows = [{ provider: 'stripe', status: 'active' }]

    await upsertSubscription({
      userId: 'u-1',
      bot: 'spark',
      status: 'canceled',
      provider: 'apple',
      currentPeriodEnd: null,
    })

    expect(executed.find((e) => e.sql.includes('INSERT INTO customer_bot_subscriptions'))).toBeUndefined()
  })

  it('refuses a Stripe event that would clobber an active Apple row', async () => {
    rows = [{ provider: 'apple', status: 'trialing' }]

    await upsertSubscription({
      userId: 'u-1',
      bot: 'flame',
      status: 'active',
      provider: 'stripe',
      currentPeriodEnd: null,
    })

    expect(executed.find((e) => e.sql.includes('INSERT INTO customer_bot_subscriptions'))).toBeUndefined()
  })

  it('allows a same-provider write even though the row is active', async () => {
    rows = [{ provider: 'stripe', status: 'active' }]

    await upsertSubscription({
      userId: 'u-1',
      bot: 'spark',
      status: 'past_due',
      provider: 'stripe',
      currentPeriodEnd: null,
    })

    expect(executed.find((e) => e.sql.includes('INSERT INTO customer_bot_subscriptions'))).toBeDefined()
  })

  it('allows a cross-provider write when the existing row is already canceled', async () => {
    rows = [{ provider: 'stripe', status: 'canceled' }]

    await upsertSubscription({
      userId: 'u-1',
      bot: 'spark',
      status: 'active',
      provider: 'apple',
      currentPeriodEnd: null,
    })

    expect(executed.find((e) => e.sql.includes('INSERT INTO customer_bot_subscriptions'))).toBeDefined()
  })

  it('allows a first-time write when no row exists yet', async () => {
    rows = []

    await upsertSubscription({
      userId: 'u-1',
      bot: 'spark',
      status: 'trialing',
      provider: 'apple',
      currentPeriodEnd: null,
    })

    expect(executed.find((e) => e.sql.includes('INSERT INTO customer_bot_subscriptions'))).toBeDefined()
  })
})
