import { describe, it, expect } from 'vitest'
import { evaluateTransaction, type DecodedTransactionLike } from '../verify-logic'

const BUNDLE_ID = 'trade.ironforge.app'
const USER_ID = 'user-123'
const NOW = new Date('2026-09-18T12:00:00Z').getTime()
const FUTURE = NOW + 30 * 24 * 60 * 60 * 1000
const PAST = NOW - 60 * 60 * 1000

function baseTransaction(overrides: Partial<DecodedTransactionLike> = {}): DecodedTransactionLike {
  return {
    bundleId: BUNDLE_ID,
    productId: 'ironforge.spark.monthly',
    originalTransactionId: 'txn-original-1',
    appAccountToken: USER_ID,
    expiresDate: FUTURE,
    ...overrides,
  }
}

describe('evaluateTransaction', () => {
  it('accepts a transaction whose appAccountToken matches the caller', () => {
    const result = evaluateTransaction(baseTransaction(), { bundleId: BUNDLE_ID, userId: USER_ID, now: NOW })
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.plan.bots).toEqual(['spark'])
      expect(result.status).toBe('active')
      expect(result.originalTransactionId).toBe('txn-original-1')
      expect(result.expiresDateIso).toBe(new Date(FUTURE).toISOString())
    }
  })

  it('rejects a bundle id that does not match APPLE_IAP_BUNDLE_ID', () => {
    const result = evaluateTransaction(baseTransaction({ bundleId: 'com.someone.else' }), {
      bundleId: BUNDLE_ID,
      userId: USER_ID,
      now: NOW,
    })
    expect(result).toEqual({ ok: false, status: 400, error: 'bad_bundle' })
  })

  it('rejects a productId not in the catalogue', () => {
    const result = evaluateTransaction(baseTransaction({ productId: 'ironforge.unknown.monthly' }), {
      bundleId: BUNDLE_ID,
      userId: USER_ID,
      now: NOW,
    })
    expect(result).toEqual({ ok: false, status: 400, error: 'unknown_product' })
  })

  it('rejects 403 when appAccountToken belongs to a different user', () => {
    const result = evaluateTransaction(baseTransaction({ appAccountToken: 'someone-else' }), {
      bundleId: BUNDLE_ID,
      userId: USER_ID,
      now: NOW,
    })
    expect(result).toEqual({ ok: false, status: 403, error: 'foreign_transaction' })
  })

  it('rejects 403 when there is no appAccountToken and the row is already owned by someone else', () => {
    const result = evaluateTransaction(baseTransaction({ appAccountToken: undefined }), {
      bundleId: BUNDLE_ID,
      userId: USER_ID,
      existingOwnerUserId: 'someone-else',
      now: NOW,
    })
    expect(result).toEqual({ ok: false, status: 403, error: 'foreign_transaction' })
  })

  it('accepts with no appAccountToken when the existing row is already this user\'s', () => {
    const result = evaluateTransaction(baseTransaction({ appAccountToken: undefined }), {
      bundleId: BUNDLE_ID,
      userId: USER_ID,
      existingOwnerUserId: USER_ID,
      now: NOW,
    })
    expect(result.ok).toBe(true)
  })

  it('accepts with no appAccountToken and no existing row at all (fresh restore)', () => {
    const result = evaluateTransaction(baseTransaction({ appAccountToken: undefined }), {
      bundleId: BUNDLE_ID,
      userId: USER_ID,
      existingOwnerUserId: null,
      now: NOW,
    })
    expect(result.ok).toBe(true)
  })

  it('rejects a transaction missing productId or originalTransactionId', () => {
    const noProduct = evaluateTransaction(baseTransaction({ productId: undefined }), {
      bundleId: BUNDLE_ID,
      userId: USER_ID,
      now: NOW,
    })
    expect(noProduct).toEqual({ ok: false, status: 400, error: 'invalid_transaction' })

    const noOriginalId = evaluateTransaction(baseTransaction({ originalTransactionId: undefined }), {
      bundleId: BUNDLE_ID,
      userId: USER_ID,
      now: NOW,
    })
    expect(noOriginalId).toEqual({ ok: false, status: 400, error: 'invalid_transaction' })
  })

  it('derives status=canceled from a revoked transaction even with a future expiresDate', () => {
    const result = evaluateTransaction(baseTransaction({ revocationDate: NOW - 1000 }), {
      bundleId: BUNDLE_ID,
      userId: USER_ID,
      now: NOW,
    })
    expect(result.ok).toBe(true)
    if (result.ok) expect(result.status).toBe('canceled')
  })

  it('derives status=canceled from an expired transaction', () => {
    const result = evaluateTransaction(baseTransaction({ expiresDate: PAST }), {
      bundleId: BUNDLE_ID,
      userId: USER_ID,
      now: NOW,
    })
    expect(result.ok).toBe(true)
    if (result.ok) expect(result.status).toBe('canceled')
  })

  it('resolves the both.monthly product to the bundle plan', () => {
    const result = evaluateTransaction(
      baseTransaction({ productId: 'ironforge.both.monthly' }),
      { bundleId: BUNDLE_ID, userId: USER_ID, now: NOW },
    )
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.plan.bundle).toBe(true)
      expect(result.plan.bots).toEqual(['spark', 'flame'])
    }
  })
})
