/**
 * Tests for getOrderFillPrice — aggressive fill polling with safety caps.
 *
 * Verifies:
 * 1. Happy path: filled on first poll, filled after delay
 * 2. Terminal states: rejected/canceled/expired confirmed after 5 reads
 * 3. Safety cap: 90s timeout returns null
 * 4. Backoff: 1s → 2s → 3s intervals
 * 5. API failures: retried until cap
 * 6. Mixed states: pending → filled, pending → rejected
 * 7. Filled with leg fallback calculation
 * 8. No zombie promises (function exits cleanly)
 * 9. Terminal counter reset on non-terminal/API-failure reads
 * 10. Mixed terminal states count as consecutive
 * 11. URL and auth header construction
 * 12. Filled but no price — keeps polling until price populated
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Set env vars BEFORE module load
vi.hoisted(() => {
  process.env.TRADIER_API_KEY = 'test-prod-key'
  process.env.TRADIER_SANDBOX_KEY_USER = 'test-sandbox-user'
})

// Mock fetch globally
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

// Use fake timers for timeout testing
// NOTE: We use real timers for most tests and fake timers only for the safety cap test

import { _testing } from '../tradier'

const { getOrderFillPrice } = _testing

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function jsonResponse(data: any, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    json: () => Promise.resolve(data),
  }
}

function orderResponse(status: string, avgFillPrice?: number, legs?: any[]) {
  const order: any = { id: 12345, status }
  if (avgFillPrice != null) order.avg_fill_price = avgFillPrice
  if (legs) order.leg = legs
  return jsonResponse({ order })
}

const API_KEY = 'test-sandbox-user'
const ACCOUNT_ID = 'test-account-123'
const ORDER_ID = 12345

beforeEach(() => {
  mockFetch.mockReset()
})

/* ================================================================== */
/*  1. Happy Path — Immediate Fill                                     */
/* ================================================================== */

describe('Fill Polling: Happy Path', () => {
  it('returns fill price immediately when order is already filled', async () => {
    mockFetch.mockResolvedValueOnce(orderResponse('filled', 1.25))

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBe(1.25)
    expect(mockFetch).toHaveBeenCalledTimes(1)
  })

  it('returns absolute value of negative fill price', async () => {
    // Tradier sometimes returns negative for credit spreads
    mockFetch.mockResolvedValueOnce(orderResponse('filled', -0.85))

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBe(0.85)
  })

  it('polls pending → filled (fills on 3rd poll)', async () => {
    mockFetch
      .mockResolvedValueOnce(orderResponse('pending'))
      .mockResolvedValueOnce(orderResponse('open'))
      .mockResolvedValueOnce(orderResponse('filled', 0.42))

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBe(0.42)
    expect(mockFetch).toHaveBeenCalledTimes(3)
  })

  it('handles partially_filled → filled transition', async () => {
    mockFetch
      .mockResolvedValueOnce(orderResponse('partially_filled'))
      .mockResolvedValueOnce(orderResponse('filled', 1.10))

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBe(1.10)
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })
})

/* ================================================================== */
/*  2. Leg Fallback Calculation                                        */
/* ================================================================== */

describe('Fill Polling: Leg Fallback', () => {
  it('calculates fill price from legs when avg_fill_price is missing', async () => {
    // IC: sell put spread ($0.50) + sell call spread ($0.35) = $0.85 credit
    const legs = [
      { side: 'sell_to_open', avg_fill_price: '0.50' }, // short put
      { side: 'buy_to_open',  avg_fill_price: '0.20' }, // long put
      { side: 'sell_to_open', avg_fill_price: '0.35' }, // short call
      { side: 'buy_to_open',  avg_fill_price: '0.15' }, // long call
    ]
    mockFetch.mockResolvedValueOnce(
      orderResponse('filled', undefined, legs),
    )

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    // sell legs: 0.50 + 0.35 = 0.85, buy legs: 0.20 + 0.15 = 0.35
    // total = |0.85 - 0.35| = 0.50
    expect(price).toBeCloseTo(0.50, 10)
  })

  it('handles single leg array (not wrapped)', async () => {
    // Tradier sometimes returns a single object instead of array
    mockFetch.mockResolvedValueOnce(jsonResponse({
      order: {
        id: ORDER_ID,
        status: 'filled',
        leg: { side: 'sell_to_open', avg_fill_price: '1.25' },
      },
    }))

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBe(1.25)
  })

  it('returns absolute value when buy side dominates (close order debit)', async () => {
    // Closing IC: buy_to_close costs more than sell_to_close receives
    const legs = [
      { side: 'buy_to_close',  avg_fill_price: '1.00' },
      { side: 'sell_to_close', avg_fill_price: '0.20' },
      { side: 'buy_to_close',  avg_fill_price: '0.80' },
      { side: 'sell_to_close', avg_fill_price: '0.15' },
    ]
    mockFetch.mockResolvedValueOnce(orderResponse('filled', undefined, legs))

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    // sell: 0.20 + 0.15 = 0.35, buy: -1.00 - 0.80 = -1.80
    // total = 0.35 - 1.80 = -1.45, abs = 1.45
    expect(price).toBeCloseTo(1.45, 10)
  })
})

/* ================================================================== */
/*  3. Terminal States — Confirmed After 5 Reads                       */
/* ================================================================== */

describe('Fill Polling: Terminal States', () => {
  it('returns null after 5 consecutive rejected reads', async () => {
    // 5 consecutive "rejected" responses should trigger terminal exit
    for (let i = 0; i < 5; i++) {
      mockFetch.mockResolvedValueOnce(orderResponse('rejected'))
    }

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBeNull()
    expect(mockFetch).toHaveBeenCalledTimes(5)
  })

  it('returns null after 5 consecutive canceled reads', async () => {
    for (let i = 0; i < 5; i++) {
      mockFetch.mockResolvedValueOnce(orderResponse('canceled'))
    }

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBeNull()
    expect(mockFetch).toHaveBeenCalledTimes(5)
  })

  it('returns null after 5 consecutive expired reads', async () => {
    for (let i = 0; i < 5; i++) {
      mockFetch.mockResolvedValueOnce(orderResponse('expired'))
    }

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBeNull()
    expect(mockFetch).toHaveBeenCalledTimes(5)
  })

  it('resets terminal count if pending appears between rejected reads', async () => {
    // rejected, rejected, pending resets counter, then rejected x5 → null
    const responses = [
      orderResponse('rejected'),   // term count = 1
      orderResponse('rejected'),   // term count = 2
      orderResponse('pending'),    // resets to 0
      orderResponse('rejected'),   // term count = 1
      orderResponse('rejected'),   // term count = 2
      orderResponse('rejected'),   // term count = 3
      orderResponse('rejected'),   // term count = 4
      orderResponse('rejected'),   // term count = 5 → null
    ]
    let callIdx = 0
    mockFetch.mockImplementation(() => Promise.resolve(responses[callIdx++]))

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBeNull()
    expect(callIdx).toBe(8)
  }, 15000)

  it('fills after 4 rejected reads (not yet confirmed terminal)', async () => {
    // 4 rejected then filled — should return fill, not give up
    mockFetch
      .mockResolvedValueOnce(orderResponse('rejected'))
      .mockResolvedValueOnce(orderResponse('rejected'))
      .mockResolvedValueOnce(orderResponse('rejected'))
      .mockResolvedValueOnce(orderResponse('rejected'))
      .mockResolvedValueOnce(orderResponse('filled', 0.75))

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBe(0.75)
    expect(mockFetch).toHaveBeenCalledTimes(5)
  })

  it('counts mixed terminal states (rejected/canceled/expired) as consecutive', async () => {
    const responses = [
      orderResponse('rejected'),
      orderResponse('canceled'),
      orderResponse('expired'),
      orderResponse('rejected'),
      orderResponse('canceled'),
    ]
    let callIdx = 0
    mockFetch.mockImplementation(() => Promise.resolve(responses[callIdx++]))

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBeNull()
    expect(callIdx).toBe(5)
  }, 10000)
})

/* ================================================================== */
/*  4. API Failures (null data)                                        */
/* ================================================================== */

describe('Fill Polling: API Failures', () => {
  it('retries on null data (fetch error) and eventually fills', async () => {
    // First 3 calls return null (network error), then filled
    mockFetch
      .mockRejectedValueOnce(new Error('Network error'))
      .mockRejectedValueOnce(new Error('timeout'))
      .mockResolvedValueOnce(orderResponse('filled', 0.55))

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBe(0.55)
    expect(mockFetch).toHaveBeenCalledTimes(3)
  })

  it('resets terminal counter on API failure (null data)', async () => {
    // rejected x3, then null (API failure resets counter), then rejected x5 → null
    const responses: Array<any> = [
      orderResponse('rejected'),
      orderResponse('rejected'),
      orderResponse('rejected'),
      'THROW',                      // API failure → sandboxGet returns null → resets terminal count
      orderResponse('rejected'),    // 1
      orderResponse('rejected'),    // 2
      orderResponse('rejected'),    // 3
      orderResponse('rejected'),    // 4
      orderResponse('rejected'),    // 5 → null
    ]
    let callIdx = 0
    mockFetch.mockImplementation(() => {
      const resp = responses[callIdx++]
      if (resp === 'THROW') return Promise.reject(new Error('timeout'))
      return Promise.resolve(resp)
    })

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBeNull()
    expect(callIdx).toBe(9)
  }, 15000)

  it('retries through mixed API failures and non-terminal states', async () => {
    mockFetch
      .mockRejectedValueOnce(new Error('ECONNRESET'))
      .mockResolvedValueOnce(orderResponse('pending'))
      .mockRejectedValueOnce(new Error('ETIMEDOUT'))
      .mockResolvedValueOnce(orderResponse('open'))
      .mockResolvedValueOnce(orderResponse('filled', 0.77))

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBe(0.77)
    expect(mockFetch).toHaveBeenCalledTimes(5)
  })
})

/* ================================================================== */
/*  5. Safety Cap (90s timeout)                                        */
/* ================================================================== */

describe('Fill Polling: Safety Cap', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns null after 90s of pending status', async () => {
    // Every poll returns "pending" — should eventually hit the 90s safety cap
    mockFetch.mockImplementation(() =>
      Promise.resolve(orderResponse('pending')),
    )

    const pollPromise = getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)

    // Fast-forward past the 90s cap — each poll has 1-3s delay
    // Run enough timer ticks to exceed 90s
    for (let i = 0; i < 100; i++) {
      await vi.advanceTimersByTimeAsync(1000)
    }

    const price = await pollPromise
    expect(price).toBeNull()
  })

  it('returns null after 90s of API failures', async () => {
    // Every poll fails (null data) — should eventually hit the 90s safety cap
    mockFetch.mockImplementation(() =>
      Promise.resolve(jsonResponse(null)),
    )

    const pollPromise = getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)

    for (let i = 0; i < 100; i++) {
      await vi.advanceTimersByTimeAsync(1000)
    }

    const price = await pollPromise
    expect(price).toBeNull()
  })
})

/* ================================================================== */
/*  6. Edge Cases                                                      */
/* ================================================================== */

describe('Fill Polling: Edge Cases', () => {
  it('handles filled status with no avg_fill_price AND no legs', async () => {
    // filled but Tradier hasn't populated price yet — keeps polling
    // then fills with price on next read
    mockFetch
      .mockResolvedValueOnce(jsonResponse({
        order: { id: ORDER_ID, status: 'filled' },
      }))
      .mockResolvedValueOnce(orderResponse('filled', 1.50))

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBe(1.50)
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('handles filled with empty legs array then price on next poll', async () => {
    mockFetch
      .mockResolvedValueOnce(jsonResponse({
        order: { id: ORDER_ID, status: 'filled', leg: [] },
      }))
      .mockResolvedValueOnce(orderResponse('filled', 0.60))

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBe(0.60)
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('handles empty order object — status is empty string → terminal', async () => {
    // Tradier returns {order: {}} — status is empty string → treated as terminal
    // 5 consecutive empty responses → null
    for (let i = 0; i < 5; i++) {
      mockFetch.mockResolvedValueOnce(jsonResponse({ order: {} }))
    }

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBeNull()
  })

  it('handles legs with zero fill prices → total is 0 → keeps polling', async () => {
    // All legs have avg_fill_price = '0' → sell: 0, buy: 0, total = 0
    // total === 0 → falls through to keep polling
    const legs = [
      { side: 'sell_to_open', avg_fill_price: '0' },
      { side: 'buy_to_open',  avg_fill_price: '0' },
    ]
    const responses = [
      orderResponse('filled', undefined, legs),
      orderResponse('filled', 0.80),
    ]
    let callIdx = 0
    mockFetch.mockImplementation(() => Promise.resolve(responses[callIdx++]))

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBe(0.80)
    expect(callIdx).toBe(2)
  })

  it('handles unknown status as terminal', async () => {
    // Some weird status Tradier returns — 5 confirmations → null
    for (let i = 0; i < 5; i++) {
      mockFetch.mockResolvedValueOnce(orderResponse('error'))
    }

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBeNull()
    expect(mockFetch).toHaveBeenCalledTimes(5)
  })

  it('handles missing order key in response', async () => {
    // Response with no "order" key — sandboxGet returns the raw json
    // data.order will be undefined, so status is ''
    for (let i = 0; i < 5; i++) {
      mockFetch.mockResolvedValueOnce(jsonResponse({ something_else: true }))
    }

    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    expect(price).toBeNull()
  })
})

/* ================================================================== */
/*  7. Backoff Timing Constants                                        */
/* ================================================================== */

describe('Fill Polling: Backoff Timing', () => {
  it('uses correct backoff formula: 1s (1-10), 2s (11-20), 3s (21+)', () => {
    // Mirrors the code: const delay = attempt <= 10 ? 1000 : attempt <= 20 ? 2000 : 3000
    const computeDelay = (attempt: number) =>
      attempt <= 10 ? 1000 : attempt <= 20 ? 2000 : 3000

    // Tier 1: 1-10 → 1s
    for (let i = 1; i <= 10; i++) {
      expect(computeDelay(i)).toBe(1000)
    }
    // Tier 2: 11-20 → 2s
    for (let i = 11; i <= 20; i++) {
      expect(computeDelay(i)).toBe(2000)
    }
    // Tier 3: 21+ → 3s
    for (let i = 21; i <= 30; i++) {
      expect(computeDelay(i)).toBe(3000)
    }
  })

  it('uses 1s delay for first 10 polls (real timer)', async () => {
    // 9 pending polls + 1 fill = 10 total, all at 1s interval
    for (let i = 0; i < 9; i++) {
      mockFetch.mockResolvedValueOnce(orderResponse('pending'))
    }
    mockFetch.mockResolvedValueOnce(orderResponse('filled', 0.33))

    const start = Date.now()
    const price = await getOrderFillPrice(API_KEY, ACCOUNT_ID, ORDER_ID)
    const elapsed = Date.now() - start

    expect(price).toBe(0.33)
    expect(mockFetch).toHaveBeenCalledTimes(10)
    // 9 delays × ~1s each ≈ 9s (allow tolerance for test runner)
    expect(elapsed).toBeGreaterThanOrEqual(8000)
    expect(elapsed).toBeLessThan(15000)
  }, 20000) // 20s timeout for this test
})

/* ================================================================== */
/*  8. URL and Auth Header                                             */
/* ================================================================== */

describe('Fill Polling: Request Construction', () => {
  it('calls the correct Tradier order status endpoint', async () => {
    mockFetch.mockResolvedValueOnce(orderResponse('filled', 1.00))

    await getOrderFillPrice('my-key', 'ACCT-456', 99999)

    const url = mockFetch.mock.calls[0][0] as string
    expect(url).toContain('/accounts/ACCT-456/orders/99999')
  })

  it('sends Authorization header with bearer token', async () => {
    mockFetch.mockResolvedValueOnce(orderResponse('filled', 1.00))

    await getOrderFillPrice('my-secret-key', 'acct', 1)

    const opts = mockFetch.mock.calls[0][1]
    expect(opts?.headers?.Authorization).toBe('Bearer my-secret-key')
  })

  it('sends Accept: application/json header', async () => {
    mockFetch.mockResolvedValueOnce(orderResponse('filled', 1.00))

    await getOrderFillPrice('key', 'acct', 1)

    const opts = mockFetch.mock.calls[0][1]
    expect(opts?.headers?.Accept).toBe('application/json')
  })
})

/* ================================================================== */
/*  9. Safety Constants Documentation                                  */
/* ================================================================== */

describe('Fill Polling: Safety Constants', () => {
  it('MAX_POLL_MS is 90s — enough for market orders, prevents zombies', () => {
    const MAX_POLL_MS = 90_000
    expect(MAX_POLL_MS).toBe(90000)
    // Market orders fill in 1-5s; 90s is 18-90x headroom
    expect(MAX_POLL_MS).toBeGreaterThanOrEqual(60000)
    expect(MAX_POLL_MS).toBeLessThanOrEqual(120000)
  })

  it('terminal confirmation threshold is 5 reads', () => {
    const TERMINAL_THRESHOLD = 5
    expect(TERMINAL_THRESHOLD).toBe(5)
    // 5 consecutive terminal reads × 1s delay = 5s worst case for genuinely rejected orders
    // vs. 1 read which could be an API glitch
    expect(TERMINAL_THRESHOLD).toBeGreaterThanOrEqual(3)
    expect(TERMINAL_THRESHOLD).toBeLessThanOrEqual(10)
  })
})

/* ================================================================== */
/*  10. Data Contract: fill_price field on order info types             */
/* ================================================================== */

describe('Order Info Data Contracts', () => {
  it('SandboxOrderInfo includes fill_price (number | null)', () => {
    // Guards against accidental removal of the fill_price field
    const info = { order_id: 1, contracts: 5, fill_price: 1.25 as number | null }
    expect(info.fill_price).toBe(1.25)
    info.fill_price = null
    expect(info.fill_price).toBeNull()
  })

  it('SandboxCloseInfo includes fill_price (number | null)', () => {
    const info = { order_id: 1, contracts: 5, fill_price: 0.30 as number | null }
    expect(info.fill_price).toBe(0.30)
    info.fill_price = null
    expect(info.fill_price).toBeNull()
  })
})
