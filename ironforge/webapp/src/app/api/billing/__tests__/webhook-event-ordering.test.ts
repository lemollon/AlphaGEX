import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

/**
 * Bug fix: Stripe delivers events at-least-once, NOT necessarily in order. A delayed,
 * retried `customer.subscription.updated(active)` arriving AFTER `subscription.deleted`
 * must not resurrect a canceled subscription. The eventId dedupe alone cannot catch this
 * — it's a DIFFERENT event, just an older one. stripe_subscription_event_order tracks the
 * latest event.created actually applied per subscription id and skips anything older.
 */

process.env.STRIPE_WEBHOOK_SECRET = 'whsec_test'

const executed: Array<{ sql: string; params: unknown[] }> = []
// last_event_created actually "stored" per subscription id, simulating the real
// compare-and-set UPDATE ... WHERE semantics in Postgres.
const orderTable = new Map<string, string>()

vi.mock('@/lib/billing/stripe', () => ({
  verifyStripeSignature: () => true,
}))

vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: () => true,
  customerExecute: vi.fn(async (sql: string, params: unknown[] = []) => {
    executed.push({ sql, params })
    if (sql.includes('INSERT INTO stripe_webhook_events')) return 1
    if (sql.includes('INSERT INTO stripe_subscription_event_order')) {
      const [subId, created] = params as [string, string]
      const stored = orderTable.get(subId)
      if (stored && created < stored) return 0 // older — the WHERE clause blocks the update
      orderTable.set(subId, created)
      return 1
    }
    return 1
  }),
  customerQuery: vi.fn(async () => []),
}))

vi.mock('@/lib/billing/membership-sync', () => ({
  upsertSubscription: vi.fn(async () => {}),
  emitMembershipEvent: vi.fn(async () => {}),
}))

const { POST } = await import('../webhook/route')
const { upsertSubscription } = await import('@/lib/billing/membership-sync')

beforeEach(() => {
  executed.length = 0
  orderTable.clear()
  vi.mocked(upsertSubscription).mockClear()
})

function subscriptionEvent(opts: { id: string; type: string; created: number; status: string; subId: string }) {
  const event = {
    id: opts.id,
    type: opts.type,
    created: opts.created,
    data: {
      object: {
        id: opts.subId,
        customer: 'cus_1',
        status: opts.status,
        metadata: { ironforge_user_id: '11111111-1111-1111-1111-111111111111', bot: 'flame' },
      },
    },
  }
  return new NextRequest('https://x/api/billing/webhook', {
    method: 'POST',
    headers: { 'stripe-signature': 'sig' },
    body: JSON.stringify(event),
  })
}

describe('POST /api/billing/webhook — out-of-order Stripe event delivery', () => {
  it('a delayed subscription.updated(active) arriving AFTER subscription.deleted does not resurrect the row', async () => {
    // Newer event first (deleted at t=200).
    const deleted = await POST(
      subscriptionEvent({ id: 'evt_2', type: 'customer.subscription.deleted', created: 200, status: 'canceled', subId: 'sub_1' }),
    )
    expect(deleted.status).toBe(200)
    expect(vi.mocked(upsertSubscription)).toHaveBeenCalledWith(expect.objectContaining({ status: 'canceled' }))
    vi.mocked(upsertSubscription).mockClear()

    // Older event delivered late (updated/active at t=100 — BEFORE the deletion).
    const stale = await POST(
      subscriptionEvent({ id: 'evt_1', type: 'customer.subscription.updated', created: 100, status: 'active', subId: 'sub_1' }),
    )
    expect(stale.status).toBe(200)
    // Must NOT have written 'active' over the already-applied cancellation.
    expect(vi.mocked(upsertSubscription)).not.toHaveBeenCalled()
  })

  it('a newer subscription.updated(active) after an older one is applied normally', async () => {
    await POST(
      subscriptionEvent({ id: 'evt_1', type: 'customer.subscription.updated', created: 100, status: 'trialing', subId: 'sub_2' }),
    )
    vi.mocked(upsertSubscription).mockClear()

    const res = await POST(
      subscriptionEvent({ id: 'evt_2', type: 'customer.subscription.updated', created: 200, status: 'active', subId: 'sub_2' }),
    )
    expect(res.status).toBe(200)
    expect(vi.mocked(upsertSubscription)).toHaveBeenCalledWith(expect.objectContaining({ status: 'active' }))
  })

  it('same-second events (e.g. checkout.session.completed and subscription.created) are never skipped as stale', async () => {
    await POST(
      subscriptionEvent({ id: 'evt_1', type: 'customer.subscription.created', created: 500, status: 'trialing', subId: 'sub_3' }),
    )
    vi.mocked(upsertSubscription).mockClear()

    const res = await POST(
      subscriptionEvent({ id: 'evt_2', type: 'customer.subscription.updated', created: 500, status: 'active', subId: 'sub_3' }),
    )
    expect(res.status).toBe(200)
    expect(vi.mocked(upsertSubscription)).toHaveBeenCalledWith(expect.objectContaining({ status: 'active' }))
  })
})
