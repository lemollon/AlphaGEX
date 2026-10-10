import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

/**
 * gap audit #184/#216: the legacy add-agent Checkout path must open the SAME
 * trading-day trial ledger (`trials`) the main enrollment funnel opens at activation,
 * so trial-close.ts ends it after TRIAL_ELIGIBLE_DAYS eligible trading days instead of
 * riding Stripe's own calendar trial_end hold to term.
 */

process.env.STRIPE_WEBHOOK_SECRET = 'whsec_test'

const executed: Array<{ sql: string; params: unknown[] }> = []

vi.mock('@/lib/billing/stripe', () => ({
  verifyStripeSignature: () => true,
}))

vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: () => true,
  customerExecute: vi.fn(async (sql: string, params: unknown[] = []) => {
    executed.push({ sql, params })
    if (sql.includes('INSERT INTO stripe_webhook_events')) return 1
    return 1
  }),
  customerQuery: vi.fn(async () => []),
}))

vi.mock('@/lib/billing/membership-sync', () => ({
  upsertSubscription: vi.fn(async () => {}),
  emitMembershipEvent: vi.fn(async () => {}),
}))

const { POST } = await import('../webhook/route')

beforeEach(() => {
  executed.length = 0
})

function checkoutCompletedRequest(overrides: Record<string, unknown> = {}) {
  const event = {
    id: 'evt_1',
    type: 'checkout.session.completed',
    data: {
      object: {
        mode: 'subscription',
        customer: 'cus_1',
        subscription: 'sub_1',
        metadata: { ironforge_user_id: '11111111-1111-1111-1111-111111111111', bot: 'flame' },
        ...overrides,
      },
    },
  }
  return new NextRequest('https://x/api/billing/webhook', {
    method: 'POST',
    headers: { 'stripe-signature': 'sig' },
    body: JSON.stringify(event),
  })
}

describe('POST /api/billing/webhook — checkout.session.completed opens the trials ledger', () => {
  it('inserts a trials row for the bot on a real subscription checkout', async () => {
    const res = await POST(checkoutCompletedRequest())
    expect(res.status).toBe(200)
    const trialsInsert = executed.find((e) => e.sql.includes('INSERT INTO trials'))
    expect(trialsInsert).toBeDefined()
    expect(trialsInsert!.params).toEqual(['11111111-1111-1111-1111-111111111111', 'flame'])
    expect(trialsInsert!.sql).toContain("WHERE trials.status = 'not_started'")
  })

  it('never opens a trials row for a setup-mode session (no subscription exists yet)', async () => {
    await POST(checkoutCompletedRequest({ mode: 'setup', subscription: undefined }))
    const trialsInsert = executed.find((e) => e.sql.includes('INSERT INTO trials'))
    expect(trialsInsert).toBeUndefined()
  })
})
