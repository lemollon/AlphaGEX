/**
 * Mocked-Tradier integration test for XSP_SWAP (R4) — attemptXspHostSwap
 * (tradier.ts), the function placeIcOrderAllAccounts calls on the two-leg
 * (put-spread-only) host path for every account type it reaches.
 *
 * Follows the SAME fetch-mocking convention as tradier.test.ts (env vars set
 * in a vi.hoisted block, fetch stubbed globally, tradier.ts imported after).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.hoisted(() => {
  process.env.TRADIER_API_KEY = 'test-production-key'
})

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

// attemptXspHostSwap persists a filled XSP leg via a dynamic
// `await import('./xsp-swap-db')` — mocked here so these tests exercise the
// order-placement DECISION only, never touching a real Postgres pool (db.ts's
// Pool is lazily constructed but would otherwise attempt a real connection).
const mockInsertXspSwapLeg = vi.fn().mockResolvedValue('leg-id')
vi.mock('../xsp-swap-db', () => ({ insertXspSwapLeg: (...args: unknown[]) => mockInsertXspSwapLeg(...args) }))

import { attemptXspHostSwap, buildOccSymbol } from '../tradier'

function jsonResponse(data: any, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    text: () => Promise.resolve(JSON.stringify(data)),
    json: () => Promise.resolve(data),
  }
}

const EXPIRATION = '2026-09-29'
const PUT_SHORT = 773
const PUT_LONG = 771
const ACCT = { name: 'Test', apiKey: 'sandbox-key', baseUrl: 'https://sandbox.tradier.com/v1', type: 'sandbox' as const }
const ACCOUNT_ID = 'ACC123'

/** Routes the shared mockFetch by URL/method, so Promise.all's two quote
 *  fetches (short/long leg) resolve correctly regardless of call order. */
function routeFetch(opts: {
  xspShortBid?: number; xspShortAsk?: number; xspShortSize?: number
  xspLongBid?: number; xspLongAsk?: number
  orderOk?: boolean; orderId?: number; fillPrice?: number
}) {
  const shortSym = buildOccSymbol('XSP', EXPIRATION, PUT_SHORT, 'P')
  const longSym = buildOccSymbol('XSP', EXPIRATION, PUT_LONG, 'P')
  mockFetch.mockImplementation((url: string, init?: any) => {
    const method = init?.method ?? 'GET'
    if (method === 'GET' && url.includes('/markets/quotes')) {
      if (url.includes(shortSym)) {
        return Promise.resolve(jsonResponse({
          quotes: { quote: { symbol: shortSym, bid: String(opts.xspShortBid ?? 0), ask: String(opts.xspShortAsk ?? 0), last: '0', bidsize: opts.xspShortSize ?? 0, asksize: opts.xspShortSize ?? 0 } },
        }))
      }
      if (url.includes(longSym)) {
        return Promise.resolve(jsonResponse({
          quotes: { quote: { symbol: longSym, bid: String(opts.xspLongBid ?? 0), ask: String(opts.xspLongAsk ?? 0), last: '0', bidsize: 999, asksize: 999 } },
        }))
      }
      return Promise.resolve(jsonResponse({ quotes: { quote: null } }))
    }
    if (method === 'POST' && url.includes('/orders')) {
      if (opts.orderOk === false) {
        return Promise.resolve(jsonResponse({ errors: { error: 'insufficient funds' } }, 400))
      }
      return Promise.resolve(jsonResponse({ order: { id: opts.orderId ?? 555 } }))
    }
    if (method === 'GET' && url.includes(`/orders/${opts.orderId ?? 555}`)) {
      return Promise.resolve(jsonResponse({ order: { status: 'filled', avg_fill_price: String(opts.fillPrice ?? 0) } }))
    }
    return Promise.resolve(jsonResponse({}))
  })
}

beforeEach(() => {
  mockFetch.mockReset()
  mockInsertXspSwapLeg.mockClear()
  delete process.env.XSP_SWAP
})
afterEach(() => {
  delete process.env.XSP_SWAP
})

describe('attemptXspHostSwap — kill switch', () => {
  it('XSP_SWAP unset makes zero network calls and returns the account unchanged', async () => {
    // no env set
    routeFetch({})
    const out = await attemptXspHostSwap({
      botName: 'flame', ticker: 'SPY', expiration: EXPIRATION,
      putShort: PUT_SHORT, putLong: PUT_LONG, acctContracts: 3,
      spyCreditPerContract: 0.50, acct: ACCT, accountId: ACCOUNT_ID, hostPositionId: 'FLAME-SPY-1',
    })
    expect(out.nSpy).toBe(3)
    expect(out.reason).toBe('xsp_swap_disabled')
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it("XSP_SWAP='off' (any non-'on' value) also makes zero network calls", async () => {
    process.env.XSP_SWAP = 'off'
    routeFetch({})
    const out = await attemptXspHostSwap({
      botName: 'flame', ticker: 'SPY', expiration: EXPIRATION,
      putShort: PUT_SHORT, putLong: PUT_LONG, acctContracts: 3,
      spyCreditPerContract: 0.50, acct: ACCT, accountId: ACCOUNT_ID, hostPositionId: 'FLAME-SPY-2',
    })
    expect(out.nSpy).toBe(3)
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('never applies to a non-SPY ticker even when the flag is on', async () => {
    process.env.XSP_SWAP = 'on'
    routeFetch({})
    const out = await attemptXspHostSwap({
      botName: 'flame', ticker: 'QQQ', expiration: EXPIRATION,
      putShort: PUT_SHORT, putLong: PUT_LONG, acctContracts: 3,
      spyCreditPerContract: 0.50, acct: ACCT, accountId: ACCOUNT_ID, hostPositionId: 'FLAME-QQQ-1',
    })
    expect(out.nSpy).toBe(3)
    expect(out.reason).toBe('not_applicable')
    expect(mockFetch).not.toHaveBeenCalled()
  })
})

describe('attemptXspHostSwap — price gate + touch depth (on)', () => {
  beforeEach(() => { process.env.XSP_SWAP = 'on' })

  it('routes min(n,2) to XSP when XSP credit clears SPY credit and touch covers it', async () => {
    // SPY credit 0.50/contract. XSP short bid 0.80, long ask 0.30 -> xsp credit 0.50 (== gate boundary, passes).
    routeFetch({ xspShortBid: 0.80, xspShortAsk: 0.85, xspShortSize: 10, xspLongBid: 0.28, xspLongAsk: 0.30, orderId: 777, fillPrice: 0.50 })
    const out = await attemptXspHostSwap({
      botName: 'flame', ticker: 'SPY', expiration: EXPIRATION,
      putShort: PUT_SHORT, putLong: PUT_LONG, acctContracts: 3,
      spyCreditPerContract: 0.50, acct: ACCT, accountId: ACCOUNT_ID, hostPositionId: 'FLAME-SPY-3',
    })
    expect(out.reason).toBe('xsp_swap_applied')
    expect(out.nSpy).toBe(1) // 3 host - min(3,2) to XSP = 1 remains on SPY
    // A POST to /orders happened for the XSP leg.
    const posted = mockFetch.mock.calls.some(([url, init]: any[]) => init?.method === 'POST' && url.includes('/orders'))
    expect(posted).toBe(true)
    expect(mockInsertXspSwapLeg).toHaveBeenCalledTimes(1)
    expect(mockInsertXspSwapLeg.mock.calls[0][0]).toMatchObject({ contracts: 2, hostPositionId: 'FLAME-SPY-3' })
  })

  it('keeps everything on SPY when XSP credit misses the gate by more than $0.05/share', async () => {
    // xsp credit = 0.80-0.36 = 0.44, spy credit 0.50 -> gap 0.06 > 0.05 allowed -> fail
    routeFetch({ xspShortBid: 0.80, xspShortAsk: 0.85, xspShortSize: 10, xspLongBid: 0.34, xspLongAsk: 0.36 })
    const out = await attemptXspHostSwap({
      botName: 'flame', ticker: 'SPY', expiration: EXPIRATION,
      putShort: PUT_SHORT, putLong: PUT_LONG, acctContracts: 3,
      spyCreditPerContract: 0.50, acct: ACCT, accountId: ACCOUNT_ID, hostPositionId: 'FLAME-SPY-4',
    })
    expect(out.reason).toBe('xsp_credit_below_gate')
    expect(out.nSpy).toBe(3)
    const postedOrder = mockFetch.mock.calls.some(([url, init]: any[]) => init?.method === 'POST' && url.includes('/orders'))
    expect(postedOrder).toBe(false)
  })

  it('keeps everything on SPY when the XSP touch is thinner than the candidate size', async () => {
    routeFetch({ xspShortBid: 0.80, xspShortAsk: 0.85, xspShortSize: 1, xspLongBid: 0.28, xspLongAsk: 0.30 })
    const out = await attemptXspHostSwap({
      botName: 'flame', ticker: 'SPY', expiration: EXPIRATION,
      putShort: PUT_SHORT, putLong: PUT_LONG, acctContracts: 3,
      spyCreditPerContract: 0.50, acct: ACCT, accountId: ACCOUNT_ID, hostPositionId: 'FLAME-SPY-5',
    })
    expect(out.reason).toBe('xsp_touch_too_thin')
    expect(out.nSpy).toBe(3)
  })

  it('falls back to 100% SPY (never skips the trade) when the XSP order itself is rejected', async () => {
    routeFetch({ xspShortBid: 0.80, xspShortAsk: 0.85, xspShortSize: 10, xspLongBid: 0.28, xspLongAsk: 0.30, orderOk: false })
    const out = await attemptXspHostSwap({
      botName: 'flame', ticker: 'SPY', expiration: EXPIRATION,
      putShort: PUT_SHORT, putLong: PUT_LONG, acctContracts: 3,
      spyCreditPerContract: 0.50, acct: ACCT, accountId: ACCOUNT_ID, hostPositionId: 'FLAME-SPY-6',
    })
    expect(out.reason).toBe('xsp_order_failed')
    expect(out.nSpy).toBe(3) // full count falls back to SPY — trade never skipped
  })

  it('routes all to SPY when the XSP quote cannot be fetched at all', async () => {
    mockFetch.mockImplementation(() => Promise.resolve(jsonResponse({ quotes: { quote: null } })))
    const out = await attemptXspHostSwap({
      botName: 'flame', ticker: 'SPY', expiration: EXPIRATION,
      putShort: PUT_SHORT, putLong: PUT_LONG, acctContracts: 3,
      spyCreditPerContract: 0.50, acct: ACCT, accountId: ACCOUNT_ID, hostPositionId: 'FLAME-SPY-7',
    })
    expect(out.reason).toBe('xsp_quote_unavailable')
    expect(out.nSpy).toBe(3)
  })

  it('caps XSP at 2 contracts even when the host has more', async () => {
    routeFetch({ xspShortBid: 0.80, xspShortAsk: 0.85, xspShortSize: 10, xspLongBid: 0.28, xspLongAsk: 0.30, orderId: 888, fillPrice: 0.50 })
    const out = await attemptXspHostSwap({
      botName: 'spark', ticker: 'SPY', expiration: EXPIRATION,
      putShort: PUT_SHORT, putLong: PUT_LONG, acctContracts: 5,
      spyCreditPerContract: 0.50, acct: ACCT, accountId: ACCOUNT_ID, hostPositionId: 'SPARK-SPY-1',
    })
    expect(out.nSpy).toBe(3) // 5 - min(5,2)
  })
})
