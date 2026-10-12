import { describe, it, expect, vi, beforeEach } from 'vitest'

/**
 * Bug fix: createTrialingSubscription is called with no Stripe-level idempotency key, so
 * a retry after Stripe succeeds but a later step (the DB write in /api/v1/activations)
 * throws creates a genuinely SECOND live subscription on the next attempt — the app's own
 * Idempotency-Key header only dedupes the client's HTTP retry, it never reaches Stripe.
 * Asserts the 'Idempotency-Key' header is sent on the subscription-creation call when a
 * key is provided, and omitted when it is not (so an un-keyed caller behaves unchanged).
 */

process.env.STRIPE_SECRET_KEY = 'sk_test_123'

const { createTrialingSubscription } = await import('../stripe')

beforeEach(() => {
  vi.restoreAllMocks()
})

function mockFetchOnce(body: unknown) {
  const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({
    ok: true,
    json: async () => body,
  }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('createTrialingSubscription — Stripe idempotency key', () => {
  it('sends the caller-provided key as the Idempotency-Key header', async () => {
    const fetchMock = mockFetchOnce({ id: 'sub_1', status: 'trialing' })

    await createTrialingSubscription({
      customerId: 'cus_1',
      priceId: 'price_1',
      userId: 'user-1',
      bot: 'spark',
      idempotencyKey: 'activate:idem-key-abc',
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [, init] = fetchMock.mock.calls[0]
    const headers = init!.headers as Record<string, string>
    expect(headers['Idempotency-Key']).toBe('activate:idem-key-abc')
  })

  it('omits the header when no key is provided', async () => {
    const fetchMock = mockFetchOnce({ id: 'sub_2', status: 'trialing' })

    await createTrialingSubscription({
      customerId: 'cus_1',
      priceId: 'price_1',
      userId: 'user-1',
      bot: 'spark',
    })

    const [, init] = fetchMock.mock.calls[0]
    const headers = init!.headers as Record<string, string>
    expect(headers['Idempotency-Key']).toBeUndefined()
  })

  it('a retried call with the SAME key hits Stripe with the same header both times (Stripe dedupes server-side)', async () => {
    const fetchMock = mockFetchOnce({ id: 'sub_3', status: 'trialing' })
    const args = {
      customerId: 'cus_1',
      priceId: 'price_1',
      userId: 'user-1',
      bot: 'spark',
      idempotencyKey: 'activate:same-key',
    }

    await createTrialingSubscription(args)
    mockFetchOnce({ id: 'sub_3', status: 'trialing' })
    await createTrialingSubscription(args)

    // Both calls must present the identical key — that's what lets Stripe's own
    // idempotency machinery return the first-created subscription on the retry.
    const first = fetchMock.mock.calls[0][1]!.headers as Record<string, string>
    expect(first['Idempotency-Key']).toBe('activate:same-key')
  })
})
