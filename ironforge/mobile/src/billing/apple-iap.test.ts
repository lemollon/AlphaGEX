import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { PurchaseIOS } from 'expo-iap'

/**
 * apple-iap.ts reaches the native expo-iap module and the authenticated api() client.
 * Neither exists in the node test environment and neither is the subject here: what
 * is under test is the purchase-flow handler logic — verify then finish, never finish
 * on rejection, retry exactly once on a network failure, stay silent on cancel. Mock
 * the edges, keep apple-iap.ts real (same convention as api/client.test.ts).
 */
const mocks = vi.hoisted(() => ({
  initConnection: vi.fn(async () => true),
  endConnection: vi.fn(async () => true),
  fetchProducts: vi.fn(async (): Promise<unknown[]> => []),
  requestPurchase: vi.fn(async () => null),
  finishTransaction: vi.fn(async () => undefined),
  getAvailablePurchases: vi.fn(async () => []),
  restorePurchasesNative: vi.fn(async () => undefined),
  purchaseUpdatedListener: vi.fn((_cb: unknown) => ({ remove: () => {} })),
  purchaseErrorListener: vi.fn((_cb: unknown) => ({ remove: () => {} })),
  api: vi.fn(),
}))

vi.mock('expo-iap', () => ({
  initConnection: mocks.initConnection,
  endConnection: mocks.endConnection,
  fetchProducts: mocks.fetchProducts,
  requestPurchase: mocks.requestPurchase,
  finishTransaction: mocks.finishTransaction,
  getAvailablePurchases: mocks.getAvailablePurchases,
  restorePurchases: mocks.restorePurchasesNative,
  purchaseUpdatedListener: mocks.purchaseUpdatedListener,
  purchaseErrorListener: mocks.purchaseErrorListener,
  isUserCancelledError: (error: { code?: string } | null | undefined) => error?.code === 'user-cancelled',
  getUserFriendlyErrorMessage: (error: { message?: string } | null | undefined) =>
    error?.message ?? 'Something went wrong.',
}))

vi.mock('@/api/client', () => {
  class ApiError extends Error {
    status: number
    body: Record<string, unknown> | null
    constructor(message: string, status: number, body: Record<string, unknown> | null) {
      super(message)
      this.name = 'ApiError'
      this.status = status
      this.body = body
    }
    get humanMessage(): string {
      const m = this.body?.message
      return typeof m === 'string' && m.trim() ? m : this.message
    }
  }
  return { api: mocks.api, ApiError }
})

const {
  handlePurchaseUpdated,
  handlePurchaseError,
  jwsFor,
  isAppleStorePurchase,
  pickNewestPerProduct,
  purchase,
  loadProducts,
} = await import('@/billing/apple-iap')
const { ApiError } = await import('@/api/client')

function makePurchase(overrides: Partial<PurchaseIOS> = {}): PurchaseIOS {
  return {
    id: 'txn-1',
    isAutoRenewing: true,
    productId: 'ironforge.spark.monthly',
    purchaseState: 'purchased',
    purchaseToken: 'jws-token-abc',
    quantity: 1,
    store: 'apple',
    transactionDate: Date.now(),
    transactionId: 'txn-1',
    ...overrides,
  } as PurchaseIOS
}

beforeEach(() => {
  mocks.api.mockReset()
  mocks.finishTransaction.mockClear()
  mocks.requestPurchase.mockClear()
  mocks.fetchProducts.mockClear()
})

describe('handlePurchaseUpdated', () => {
  it('success: verifies with the purchaseToken as the JWS, then finishes the transaction', async () => {
    mocks.api.mockResolvedValueOnce({ ok: true })
    const onError = vi.fn()
    const p = makePurchase()

    const result = await handlePurchaseUpdated(p, onError)

    expect(mocks.api).toHaveBeenCalledWith('/api/billing/apple/verify', {
      method: 'POST',
      body: { jws: 'jws-token-abc' },
    })
    expect(mocks.finishTransaction).toHaveBeenCalledWith({ purchase: p, isConsumable: false })
    expect(onError).not.toHaveBeenCalled()
    expect(result).toEqual({ ok: true })
  })

  it('verify 403: does not finish, does not retry, and surfaces the server message', async () => {
    mocks.api.mockRejectedValueOnce(
      new ApiError('Forbidden', 403, { message: 'This purchase belongs to another account.' }),
    )
    const onError = vi.fn()
    const p = makePurchase()

    const result = await handlePurchaseUpdated(p, onError)

    expect(mocks.api).toHaveBeenCalledTimes(1)
    expect(mocks.finishTransaction).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalledWith('This purchase belongs to another account.')
    expect(result).toEqual({
      ok: false,
      reason: 'rejected',
      message: 'This purchase belongs to another account.',
    })
  })

  it('network failure: retries exactly once, then surfaces an error without finishing', async () => {
    mocks.api.mockRejectedValueOnce(new TypeError('Network request failed'))
    mocks.api.mockRejectedValueOnce(new TypeError('Network request failed'))
    const onError = vi.fn()
    const p = makePurchase()

    const result = await handlePurchaseUpdated(p, onError)

    expect(mocks.api).toHaveBeenCalledTimes(2)
    expect(mocks.finishTransaction).not.toHaveBeenCalled()
    expect(result).toEqual({ ok: false, reason: 'network' })
    expect(onError).toHaveBeenCalledWith(
      'Could not reach IronForge to confirm your purchase. It will retry automatically.',
    )
  })

  it('recovers if the retry succeeds — verifies, then finishes', async () => {
    mocks.api.mockRejectedValueOnce(new TypeError('Network request failed'))
    mocks.api.mockResolvedValueOnce({ ok: true })
    const p = makePurchase()

    const result = await handlePurchaseUpdated(p)

    expect(mocks.api).toHaveBeenCalledTimes(2)
    expect(mocks.finishTransaction).toHaveBeenCalledWith({ purchase: p, isConsumable: false })
    expect(result).toEqual({ ok: true })
  })

  it('never calls verify or finish when the purchase carries no token', async () => {
    const onError = vi.fn()
    const p = makePurchase({ purchaseToken: null })

    const result = await handlePurchaseUpdated(p, onError)

    expect(mocks.api).not.toHaveBeenCalled()
    expect(mocks.finishTransaction).not.toHaveBeenCalled()
    expect(result).toEqual({ ok: false, reason: 'no_jws' })
    expect(onError).toHaveBeenCalledWith('This purchase could not be verified. Please contact support.')
  })
})

describe('handlePurchaseError (purchase-error listener)', () => {
  it('cancel: is silent — no onError call', () => {
    const onError = vi.fn()
    handlePurchaseError({ code: 'user-cancelled', message: 'User cancelled' } as never, onError)
    expect(onError).not.toHaveBeenCalled()
  })

  it('every other error surfaces expo-iap’s friendly message', () => {
    const onError = vi.fn()
    handlePurchaseError({ code: 'network-error', message: 'Store unreachable' } as never, onError)
    expect(onError).toHaveBeenCalledWith('Store unreachable')
  })
})

describe('jwsFor / isAppleStorePurchase', () => {
  it('extracts the unified purchaseToken as the JWS for an Apple purchase', () => {
    const p = makePurchase({ purchaseToken: 'the-jws' })
    expect(isAppleStorePurchase(p)).toBe(true)
    expect(jwsFor(p)).toBe('the-jws')
  })

  it('is null for a non-Apple purchase', () => {
    const p = makePurchase({ store: 'google', purchaseToken: 'android-token' })
    expect(isAppleStorePurchase(p)).toBe(false)
    expect(jwsFor(p)).toBeNull()
  })
})

describe('pickNewestPerProduct', () => {
  it('keeps only the latest-expiry transaction per product', () => {
    const stale = makePurchase({ id: 'a', productId: 'ironforge.spark.monthly', expirationDateIOS: 1000 })
    const fresh = makePurchase({ id: 'b', productId: 'ironforge.spark.monthly', expirationDateIOS: 5000 })
    const other = makePurchase({ id: 'c', productId: 'ironforge.flame.monthly', expirationDateIOS: 2000 })

    const result = pickNewestPerProduct([stale, fresh, other])

    expect(result).toHaveLength(2)
    expect(result.find((p) => p.productId === 'ironforge.spark.monthly')?.id).toBe('b')
    expect(result.find((p) => p.productId === 'ironforge.flame.monthly')?.id).toBe('c')
  })
})

describe('purchase', () => {
  it('requests a subscription purchase with appAccountToken set to the user id', async () => {
    await purchase('ironforge.spark.monthly', 'user-123')

    expect(mocks.requestPurchase).toHaveBeenCalledWith({
      type: 'subs',
      request: { apple: { sku: 'ironforge.spark.monthly', appAccountToken: 'user-123' } },
    })
  })
})

describe('loadProducts', () => {
  it('maps StoreKit products to id/title/displayPrice', async () => {
    mocks.fetchProducts.mockResolvedValueOnce([
      { id: 'ironforge.spark.monthly', title: 'IronForge Spark', displayPrice: '$50.00', type: 'subs' },
    ])

    const products = await loadProducts()

    expect(mocks.fetchProducts).toHaveBeenCalledWith({
      skus: [
        'ironforge.both.monthly',
        'ironforge.spark.monthly',
        'ironforge.flame.monthly',
        'ironforge.community.monthly',
      ],
      type: 'subs',
    })
    expect(products).toEqual([
      { productId: 'ironforge.spark.monthly', title: 'IronForge Spark', displayPrice: '$50.00' },
    ])
  })
})
