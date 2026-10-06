import { describe, it, expect, vi, beforeEach } from 'vitest'

/**
 * Mobile's GET /api/billing/membership carries the same "trial ending soon" signal as
 * the web dashboard's lib/live/membership.ts (gap audit #212, "Trial ending ... Banner 1
 * trading day before trial end" — mobile + web must agree on the same trading-day ledger).
 */

const USER_ID = 'u-1'

let subRows: Array<{ bot: string; status: string; provider: string; price_lookup_key: string | null; current_period_end: string | null }> = []
let ledgerRows: Array<{ eligible_days_used: string | null }> = []

vi.mock('@/lib/customers-db', () => ({
  customerQuery: vi.fn(async (sql: string) => {
    if (sql.includes('FROM customer_bot_subscriptions')) return subRows
    if (sql.includes('FROM trials')) return ledgerRows
    return []
  }),
}))

const { buildMembershipResponse } = await import('../membership')

beforeEach(() => {
  subRows = []
  ledgerRows = []
})

describe('buildMembershipResponse — trial_ending_soon', () => {
  it('is false for an active (non-trialing) subscription', async () => {
    subRows = [{ bot: 'spark', status: 'active', provider: 'stripe', price_lookup_key: 'spark_monthly', current_period_end: null }]
    const res = await buildMembershipResponse(USER_ID)
    expect(res.membership?.trial_ending_soon).toBe(false)
  })

  it('is true with 1 eligible trading day left', async () => {
    subRows = [{ bot: 'spark', status: 'trialing', provider: 'stripe', price_lookup_key: 'spark_monthly', current_period_end: null }]
    ledgerRows = [{ eligible_days_used: '4' }]
    const res = await buildMembershipResponse(USER_ID)
    expect(res.membership?.trial_ending_soon).toBe(true)
  })

  it('is false with 2+ eligible trading days left', async () => {
    subRows = [{ bot: 'spark', status: 'trialing', provider: 'stripe', price_lookup_key: 'spark_monthly', current_period_end: null }]
    ledgerRows = [{ eligible_days_used: '1' }]
    const res = await buildMembershipResponse(USER_ID)
    expect(res.membership?.trial_ending_soon).toBe(false)
  })

  it('a past_due row still reports status past_due regardless of trial_ending_soon', async () => {
    subRows = [{ bot: 'spark', status: 'past_due', provider: 'stripe', price_lookup_key: 'spark_monthly', current_period_end: null }]
    const res = await buildMembershipResponse(USER_ID)
    expect(res.membership?.status).toBe('past_due')
    expect(res.membership?.trial_ending_soon).toBe(false)
  })
})
