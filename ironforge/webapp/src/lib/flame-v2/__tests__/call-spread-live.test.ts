/**
 * flame-v2/call-spread-live.ts — the FLAME v2 SPY 0DTE CALL credit spread
 * orchestration: entry tick, mirrored assignment-guard tick, settle tick.
 * flameCallSpreadDecision (engine.ts) and the Tradier/DB layers are mocked
 * so these tests isolate exactly this module's own logic: idempotency, the
 * min-credit floor, shadow-vs-live order placement, and the guard's
 * paper-vs-live close paths.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const dbCalls: Array<{ sql: string; params?: any[] }> = []
const mockQuery = vi.fn(async (sql: string, params?: any[]) => {
  dbCalls.push({ sql, params })
  return queryResults.shift() ?? []
})
const mockDbExecute = vi.fn(async (sql: string, params?: any[]) => {
  dbCalls.push({ sql, params })
  return 1
})
let queryResults: any[] = []

vi.mock('@/lib/db', () => ({
  query: (...a: any[]) => mockQuery(a[0], a[1]),
  dbExecute: (...a: any[]) => mockDbExecute(a[0], a[1]),
}))

const mockGetQuote = vi.fn()
const mockGetOptionQuote = vi.fn()
const mockGetDailyHistory = vi.fn(async () => [])
const mockCanPlaceLiveOrders = vi.fn(() => false)
const mockPlaceOrder = vi.fn(async () => ({}))

vi.mock('@/lib/tradier', () => ({
  getQuote: (...a: any[]) => mockGetQuote(...a),
  getOptionQuote: (...a: any[]) => mockGetOptionQuote(...a),
  buildOccSymbol: (t: string, e: string, k: number, cp: string) => `${t}${e}${cp}${k}`,
  getDailyHistory: (...a: any[]) => mockGetDailyHistory(...a),
  canPlaceLiveOrders: (...a: any[]) => mockCanPlaceLiveOrders(...a),
  placeFlameV2CallSpreadOrder: (...a: any[]) => mockPlaceOrder(...a),
}))

vi.mock('@/lib/market-calendar', () => ({
  marketCloseMinuteCT: () => 1500,
}))

const mockDecision = vi.fn()
vi.mock('../engine', () => ({
  flameCallSpreadDecision: (...a: any[]) => mockDecision(...a),
}))

import {
  runFlameV2CallSpreadEntryTick,
  runFlameV2CallSpreadGuardTick,
  runFlameV2CallSpreadSettleTick,
} from '../call-spread-live'

function quote(bid: number, ask: number) {
  return { bid, ask, last: (bid + ask) / 2 }
}

beforeEach(() => {
  delete process.env.FLAME_V2_CALL_SPREAD_MODE
  dbCalls.length = 0
  queryResults = []
  mockQuery.mockClear()
  mockDbExecute.mockClear()
  mockGetQuote.mockReset()
  mockGetOptionQuote.mockReset()
  mockGetDailyHistory.mockReset().mockResolvedValue([])
  mockCanPlaceLiveOrders.mockReset().mockReturnValue(false)
  mockPlaceOrder.mockReset().mockResolvedValue({})
  mockDecision.mockReset()
})
afterEach(() => {
  delete process.env.FLAME_V2_CALL_SPREAD_MODE
})

function ctAt(hh: number, mm: number): Date {
  const d = new Date()
  d.setHours(hh, mm, 0, 0)
  return d
}

describe('entry tick', () => {
  it('mode off (explicit): zero DB/decision calls', async () => {
    process.env.FLAME_V2_CALL_SPREAD_MODE = 'off'
    const r = await runFlameV2CallSpreadEntryTick('2026-10-02', 650, 2)
    expect(r).toBe('')
    expect(mockDecision).not.toHaveBeenCalled()
    expect(dbCalls.length).toBe(0)
  })

  it('shadow (default): writes the PAPER row, never calls placeFlameV2CallSpreadOrder', async () => {
    process.env.FLAME_V2_CALL_SPREAD_MODE = 'shadow'
    mockDecision.mockResolvedValue({ available: true, tier: 3, contracts: 6, shortStrike: 652, longStrike: 654, reason: 'ok_shadow' })
    queryResults = [[{ cnt: '0' }]] // "already today" check -> none yet
    mockGetOptionQuote
      .mockResolvedValueOnce(quote(0.30, 0.35)) // short call
      .mockResolvedValueOnce(quote(0.05, 0.08)) // long call
    const r = await runFlameV2CallSpreadEntryTick('2026-10-02', 650, 2)
    expect(r).toContain('traded@')
    expect(mockPlaceOrder).not.toHaveBeenCalled()
    const insert = dbCalls.find((c) => c.sql.includes('INSERT INTO flame_v2_call_positions'))
    expect(insert).toBeTruthy()
  })

  it('live + armed: places the real order with the right strikes/contracts/credit', async () => {
    process.env.FLAME_V2_CALL_SPREAD_MODE = 'live'
    mockDecision.mockResolvedValue({ available: true, tier: 1, contracts: 2, shortStrike: 652, longStrike: 654, reason: 'ok_live' })
    queryResults = [[{ cnt: '0' }]]
    mockGetOptionQuote
      .mockResolvedValueOnce(quote(0.30, 0.35))
      .mockResolvedValueOnce(quote(0.05, 0.08))
    mockCanPlaceLiveOrders.mockReturnValue(true)
    mockPlaceOrder.mockResolvedValue({ 'User:sandbox': { order_id: 1, contracts: 2, fill_price: 0.26, account_type: 'sandbox' } })
    const r = await runFlameV2CallSpreadEntryTick('2026-10-02', 650, 2)
    expect(mockPlaceOrder).toHaveBeenCalledTimes(1)
    const args = mockPlaceOrder.mock.calls[0]
    expect(args[2]).toBe(652) // callShort
    expect(args[3]).toBe(654) // callLong
    expect(args[4]).toBe(2) // contracts
    expect(r).toContain('live:1acct')
  })

  it('live but disarmed: paper row still written, no order call', async () => {
    process.env.FLAME_V2_CALL_SPREAD_MODE = 'live'
    mockDecision.mockResolvedValue({ available: true, tier: 1, contracts: 2, shortStrike: 652, longStrike: 654, reason: 'ok_live' })
    queryResults = [[{ cnt: '0' }]]
    mockGetOptionQuote
      .mockResolvedValueOnce(quote(0.30, 0.35))
      .mockResolvedValueOnce(quote(0.05, 0.08))
    mockCanPlaceLiveOrders.mockReturnValue(false)
    const r = await runFlameV2CallSpreadEntryTick('2026-10-02', 650, 2)
    expect(mockPlaceOrder).not.toHaveBeenCalled()
    expect(r).toContain('live:disarmed')
  })

  it('min credit floor ($0.10): skips, no order, no insert', async () => {
    process.env.FLAME_V2_CALL_SPREAD_MODE = 'live'
    mockDecision.mockResolvedValue({ available: true, tier: 1, contracts: 2, shortStrike: 652, longStrike: 654, reason: 'ok_live' })
    queryResults = [[{ cnt: '0' }]]
    mockGetOptionQuote
      .mockResolvedValueOnce(quote(0.05, 0.06)) // short call bid
      .mockResolvedValueOnce(quote(0.03, 0.04)) // long call ask -> credit ~0.02
    mockCanPlaceLiveOrders.mockReturnValue(true)
    const r = await runFlameV2CallSpreadEntryTick('2026-10-02', 650, 2)
    expect(r).toContain('skip:credit_low')
    expect(mockPlaceOrder).not.toHaveBeenCalled()
    expect(dbCalls.find((c) => c.sql.includes('INSERT INTO flame_v2_call_positions'))).toBeFalsy()
  })

  it('already traded today: no-ops without re-pricing', async () => {
    process.env.FLAME_V2_CALL_SPREAD_MODE = 'shadow'
    mockDecision.mockResolvedValue({ available: true, tier: 1, contracts: 1, shortStrike: 652, longStrike: 654, reason: 'ok_shadow' })
    queryResults = [[{ cnt: '1' }]]
    const r = await runFlameV2CallSpreadEntryTick('2026-10-02', 650, 2)
    expect(r).toBe('')
    expect(mockGetOptionQuote).not.toHaveBeenCalled()
  })

  it('decision unavailable: skip, no DB writes', async () => {
    process.env.FLAME_V2_CALL_SPREAD_MODE = 'shadow'
    mockDecision.mockResolvedValue({ available: false, tier: 0, contracts: 0, shortStrike: null, longStrike: null, reason: 'signals_unavailable(x)' })
    const r = await runFlameV2CallSpreadEntryTick('2026-10-02', 650, 2)
    expect(r).toContain('skip:signals_unavailable')
    expect(dbCalls.length).toBe(0)
  })
})

describe('guard tick', () => {
  it('outside the 3-minute window: no-op', async () => {
    process.env.FLAME_V2_CALL_SPREAD_MODE = 'live'
    const r = await runFlameV2CallSpreadGuardTick(ctAt(13, 0))
    expect(r).toBe('')
    expect(dbCalls.length).toBe(0)
  })

  it('spot clear of the short strike: reports clear, no close', async () => {
    process.env.FLAME_V2_CALL_SPREAD_MODE = 'live'
    queryResults = [[{ id: 1, position_id: 'P1', expiration: '2026-10-02', short_strike: 660, long_strike: 662, contracts: 2, credit: 0.30, person: 'PAPER', account_type: 'sandbox', sandbox_order_id: null }]]
    mockGetQuote.mockResolvedValue({ last: 655 })
    const r = await runFlameV2CallSpreadGuardTick(ctAt(14, 58))
    expect(r).toContain('clear@')
    expect(mockPlaceOrder).not.toHaveBeenCalled()
  })

  it('PAPER row at risk: closes directly in the DB, no broker order', async () => {
    process.env.FLAME_V2_CALL_SPREAD_MODE = 'live'
    queryResults = [[{ id: 1, position_id: 'P1', expiration: '2026-10-02', short_strike: 650, long_strike: 652, contracts: 2, credit: 0.30, person: 'PAPER', account_type: 'sandbox', sandbox_order_id: null }]]
    mockGetQuote.mockResolvedValue({ last: 650.2 }) // >= shortStrike - 0.50 buffer
    const r = await runFlameV2CallSpreadGuardTick(ctAt(14, 58))
    expect(r).toContain('guarded_paper@')
    expect(mockPlaceOrder).not.toHaveBeenCalled()
    expect(dbCalls.some((c) => c.sql.includes('UPDATE flame_v2_call_positions') && c.sql.includes('assignment_guard'))).toBe(true)
  })

  it('live row at risk: calls placeFlameV2CallSpreadOrder with close:true and the row owner', async () => {
    process.env.FLAME_V2_CALL_SPREAD_MODE = 'live'
    queryResults = [[{ id: 2, position_id: 'P2', expiration: '2026-10-02', short_strike: 650, long_strike: 652, contracts: 1, credit: 0.30, person: 'User', account_type: 'sandbox', sandbox_order_id: null }]]
    mockGetQuote.mockResolvedValue({ last: 651 })
    mockPlaceOrder.mockResolvedValue({ 'User:sandbox': { order_id: 99, contracts: 1, fill_price: 0.10, account_type: 'sandbox' } })
    const r = await runFlameV2CallSpreadGuardTick(ctAt(14, 58))
    expect(mockPlaceOrder).toHaveBeenCalledTimes(1)
    const opts = mockPlaceOrder.mock.calls[0][7]
    expect(opts).toMatchObject({ close: true, targetPerson: 'User', targetAccountType: 'sandbox' })
    expect(r).toContain('guarded@')
  })

  it('already has a pending close order: does not re-place', async () => {
    process.env.FLAME_V2_CALL_SPREAD_MODE = 'live'
    queryResults = [[{ id: 3, position_id: 'P3', expiration: '2026-10-02', short_strike: 650, long_strike: 652, contracts: 1, credit: 0.30, person: 'User', account_type: 'sandbox', sandbox_order_id: '{"User:sandbox":{}}' }]]
    mockGetQuote.mockResolvedValue({ last: 651 })
    const r = await runFlameV2CallSpreadGuardTick(ctAt(14, 58))
    expect(r).toContain('guard_pending')
    expect(mockPlaceOrder).not.toHaveBeenCalled()
  })
})

describe('settle tick', () => {
  it('before the close: no-op', async () => {
    process.env.FLAME_V2_CALL_SPREAD_MODE = 'live'
    const r = await runFlameV2CallSpreadSettleTick(ctAt(14, 0))
    expect(r).toBe('')
    expect(dbCalls.length).toBe(0)
  })

  it('settles any still-open row from the official daily close', async () => {
    process.env.FLAME_V2_CALL_SPREAD_MODE = 'live'
    queryResults = [[{ id: 1, position_id: 'P1', short_strike: 650, long_strike: 652, credit: 0.30, contracts: 2, person: 'PAPER' }]]
    const ct = ctAt(15, 1)
    mockGetDailyHistory.mockResolvedValue([{ date: ct.toISOString().slice(0, 10), close: 648 }])
    const r = await runFlameV2CallSpreadSettleTick(ct)
    expect(r).toContain('settled@')
    expect(dbCalls.some((c) => c.sql.includes("close_reason='expiry_settlement'"))).toBe(true)
  })
})
