import { describe, it, expect, vi, beforeEach } from 'vitest'

/**
 * db-states "Trial ending / payment failed" banner inputs (gap audit #212).
 *
 * getMembership() is the single place that knows both facts — a trial 1 eligible
 * trading day from ending, and a past_due subscription — so the banner never has to
 * re-derive them from raw subscription rows.
 */

const USER_ID = 'u-1'

let subRows: Array<{ bot: string; status: string; price_lookup_key: string | null; current_period_end: string | null }> = []
let ledgerRows: Array<{ eligible_days_used: string | null }> = []

vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: () => true,
  customerQuery: vi.fn(async (sql: string) => {
    if (sql.includes('FROM customer_bot_subscriptions')) return subRows
    if (sql.includes('FROM trials')) return ledgerRows
    return []
  }),
}))

const { getMembership } = await import('../membership')

beforeEach(() => {
  subRows = []
  ledgerRows = []
})

describe('getMembership — trial-ending and payment-failed flags', () => {
  it('flags payment failed when a subscription is past_due', async () => {
    subRows = [{ bot: 'spark', status: 'past_due', price_lookup_key: 'spark_monthly', current_period_end: null }]
    const card = await getMembership(USER_ID)
    expect(card.paymentFailed).toBe(true)
    expect(card.badge).toBe('Payment due')
  })

  it('does not flag payment failed for an active subscription', async () => {
    subRows = [{ bot: 'spark', status: 'active', price_lookup_key: 'spark_monthly', current_period_end: null }]
    const card = await getMembership(USER_ID)
    expect(card.paymentFailed).toBe(false)
  })

  it('flags trial ending with exactly 1 eligible trading day left', async () => {
    subRows = [{ bot: 'spark', status: 'trialing', price_lookup_key: 'spark_monthly', current_period_end: null }]
    ledgerRows = [{ eligible_days_used: '4' }] // 5 - 4 = 1 remaining
    const card = await getMembership(USER_ID)
    expect(card.trialEndingSoon).toBe(true)
    expect(card.trial?.day).toBe(5)
  })

  it('does not flag trial ending with 2+ eligible trading days left', async () => {
    subRows = [{ bot: 'spark', status: 'trialing', price_lookup_key: 'spark_monthly', current_period_end: null }]
    ledgerRows = [{ eligible_days_used: '2' }] // 5 - 2 = 3 remaining
    const card = await getMembership(USER_ID)
    expect(card.trialEndingSoon).toBe(false)
  })

  it('flags trial ending once every eligible day is used', async () => {
    subRows = [{ bot: 'spark', status: 'trialing', price_lookup_key: 'spark_monthly', current_period_end: null }]
    ledgerRows = [{ eligible_days_used: '5' }]
    const card = await getMembership(USER_ID)
    expect(card.trialEndingSoon).toBe(true)
  })
})
