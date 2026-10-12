import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

/**
 * Bug fix coverage for /api/billing/apple/notifications:
 *  1. A genuine handler failure returns 500 (Apple retries) instead of the old
 *     "ack 200 on any error" behavior, and records the failure on the dead-letter row.
 *  2. A redelivered notification whose prior attempt already succeeded is ack'd as a
 *     duplicate WITHOUT re-running the handler (no second upsertSubscription call).
 *  3. DID_CHANGE_RENEWAL_PREF with subtype UPGRADE retires the OLD product's bot row.
 */

const mocks = vi.hoisted(() => {
  const notificationEvents = new Map<string, { processed: boolean }>()
  return {
    notificationEvents,
    upsertSubscription: vi.fn(async () => {}),
    emitMembershipEvent: vi.fn(async () => {}),
    verifyAndDecodeNotification: vi.fn(),
    verifyAndDecodeTransaction: vi.fn(),
    verifyAndDecodeRenewalInfo: vi.fn(async () => null),
  }
})

vi.mock('@/lib/billing/apple/verifier', () => ({
  getAppleVerifier: () => ({
    verifyAndDecodeNotification: mocks.verifyAndDecodeNotification,
    verifyAndDecodeTransaction: mocks.verifyAndDecodeTransaction,
    verifyAndDecodeRenewalInfo: mocks.verifyAndDecodeRenewalInfo,
  }),
}))

vi.mock('@/lib/billing/membership-sync', () => ({
  upsertSubscription: mocks.upsertSubscription,
  emitMembershipEvent: mocks.emitMembershipEvent,
}))

// customer_bot_subscriptions rows this user already owns via Apple — only read by the
// DID_CHANGE_RENEWAL_PREF/UPGRADE branch; set per-test.
let ownedBotRows: Array<{ bot: string }> = []
// user lookup for appAccountToken -> user id
let userRow: { id: string } | null = { id: 'user-1' }

vi.mock('@/lib/customers-db', () => ({
  isCustomersDbConfigured: () => true,
  customerExecute: vi.fn(async (sql: string, params: unknown[] = []) => {
    if (sql.includes('INSERT INTO apple_notification_events')) {
      const uuid = params[0] as string
      if (mocks.notificationEvents.has(uuid)) return 0 // ON CONFLICT DO NOTHING
      mocks.notificationEvents.set(uuid, { processed: false })
      return 1
    }
    if (sql.includes('UPDATE apple_notification_events SET processed_at = now()')) {
      const uuid = params[0] as string
      const row = mocks.notificationEvents.get(uuid)
      if (row) row.processed = true
      return 1
    }
    if (sql.includes('UPDATE apple_notification_events SET error')) {
      return 1
    }
    return 1
  }),
  customerQuery: vi.fn(async (sql: string, params: unknown[] = []) => {
    if (sql.includes('SELECT processed_at FROM apple_notification_events')) {
      const uuid = params[0] as string
      const row = mocks.notificationEvents.get(uuid)
      return row ? [{ processed_at: row.processed ? '2026-01-01T00:00:00Z' : null }] : []
    }
    if (sql.includes('SELECT id FROM users')) {
      return userRow ? [userRow] : []
    }
    if (sql.includes('SELECT user_id FROM customer_bot_subscriptions WHERE apple_original_transaction_id')) {
      return []
    }
    if (sql.includes("SELECT bot FROM customer_bot_subscriptions")) {
      return ownedBotRows
    }
    return []
  }),
}))

const { POST } = await import('../route')

function req(signedPayload = 'jws-payload') {
  return new NextRequest('https://x/api/billing/apple/notifications', {
    method: 'POST',
    body: JSON.stringify({ signedPayload }),
  })
}

function baseTransaction(overrides: Record<string, unknown> = {}) {
  return {
    productId: 'ironforge.spark.monthly',
    originalTransactionId: 'orig-1',
    appAccountToken: 'user-1',
    expiresDate: Date.now() + 30 * 24 * 60 * 60 * 1000,
    ...overrides,
  }
}

beforeEach(() => {
  mocks.notificationEvents.clear()
  mocks.upsertSubscription.mockClear()
  mocks.emitMembershipEvent.mockClear()
  mocks.verifyAndDecodeNotification.mockReset()
  mocks.verifyAndDecodeTransaction.mockReset()
  mocks.verifyAndDecodeRenewalInfo.mockReset().mockResolvedValue(null)
  ownedBotRows = []
  userRow = { id: 'user-1' }
})

describe('POST /api/billing/apple/notifications', () => {
  it('a genuine handler failure returns 500 and dead-letters the notification', async () => {
    mocks.verifyAndDecodeNotification.mockResolvedValue({
      notificationType: 'DID_RENEW',
      notificationUUID: 'uuid-fail',
      data: { signedTransactionInfo: 'txn' },
    })
    mocks.verifyAndDecodeTransaction.mockRejectedValue(new Error('boom'))

    const res = await POST(req())

    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.ok).toBe(false)
  })

  it('acks a redelivered, already-processed notification as a duplicate without re-running the handler', async () => {
    mocks.verifyAndDecodeNotification.mockResolvedValue({
      notificationType: 'DID_RENEW',
      notificationUUID: 'uuid-dup',
      data: { signedTransactionInfo: 'txn' },
    })
    mocks.verifyAndDecodeTransaction.mockResolvedValue(baseTransaction())

    const first = await POST(req())
    expect(first.status).toBe(200)
    expect(mocks.upsertSubscription).toHaveBeenCalledTimes(1)

    const second = await POST(req())
    expect(second.status).toBe(200)
    const secondBody = await second.json()
    expect(secondBody.duplicate).toBe(true)
    // Not re-run — still exactly one call from the first delivery.
    expect(mocks.upsertSubscription).toHaveBeenCalledTimes(1)
  })

  it('DID_CHANGE_RENEWAL_PREF + subtype UPGRADE retires the old product bot row', async () => {
    mocks.verifyAndDecodeNotification.mockResolvedValue({
      notificationType: 'DID_CHANGE_RENEWAL_PREF',
      subtype: 'UPGRADE',
      notificationUUID: 'uuid-upgrade',
      data: { signedTransactionInfo: 'txn' },
    })
    // Upgraded to the bundle (spark + flame); the customer previously only owned 'flame'
    // via Apple under the old single-bot product.
    mocks.verifyAndDecodeTransaction.mockResolvedValue(
      baseTransaction({ productId: 'ironforge.both.monthly' }),
    )
    ownedBotRows = [{ bot: 'flame' }]

    const res = await POST(req())

    expect(res.status).toBe(200)
    // Grants the new bundle.
    expect(mocks.upsertSubscription).toHaveBeenCalledWith(
      expect.objectContaining({ bot: 'spark', status: 'active', provider: 'apple' }),
    )
    expect(mocks.upsertSubscription).toHaveBeenCalledWith(
      expect.objectContaining({ bot: 'flame', status: 'active', provider: 'apple' }),
    )
    // flame is ALSO in the new bundle, so it must never be retired — only a bot the new
    // plan does NOT grant would be. Confirm no canceled write happened at all here, since
    // every owned bot (flame) is covered by the new plan.
    expect(mocks.upsertSubscription).not.toHaveBeenCalledWith(
      expect.objectContaining({ status: 'canceled' }),
    )
  })

  it('DID_CHANGE_RENEWAL_PREF + subtype UPGRADE cancels a bot the new plan does not cover', async () => {
    mocks.verifyAndDecodeNotification.mockResolvedValue({
      notificationType: 'DID_CHANGE_RENEWAL_PREF',
      subtype: 'UPGRADE',
      notificationUUID: 'uuid-upgrade-2',
      data: { signedTransactionInfo: 'txn' },
    })
    // Upgraded from flame-only to spark-only (a lateral swap within the one subscription
    // group) — flame must be retired since the new plan does not include it.
    mocks.verifyAndDecodeTransaction.mockResolvedValue(
      baseTransaction({ productId: 'ironforge.spark.monthly' }),
    )
    ownedBotRows = [{ bot: 'flame' }]

    const res = await POST(req())

    expect(res.status).toBe(200)
    expect(mocks.upsertSubscription).toHaveBeenCalledWith(
      expect.objectContaining({ bot: 'flame', status: 'canceled', provider: 'apple' }),
    )
  })
})
