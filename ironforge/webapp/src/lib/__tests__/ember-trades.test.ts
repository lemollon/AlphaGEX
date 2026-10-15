/**
 * EMBER trade book — pins the upsert-by-source_ref idempotency contract
 * (ON CONFLICT (source_ref) DO UPDATE, never a second INSERT path) and the
 * read shapes the API routes depend on. Mocks ../db the same way
 * calldiag-tracker.test.ts does.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

const queryCalls: Array<{ sql: string; params?: unknown[] }> = []
const execCalls: string[] = []
let queryReturn: unknown[] = []

vi.mock('../db', () => ({
  query: vi.fn(async (sql: string, params?: unknown[]) => {
    queryCalls.push({ sql, params })
    return queryReturn
  }),
  dbExecute: vi.fn(async (sql: string) => {
    execCalls.push(sql)
  }),
}))

import {
  upsertEmberTrade,
  getEmberTrades,
  upsertEmberStatus,
  getEmberStatus,
  getEmberEquityCurve,
} from '../ember-trades'

afterEach(() => {
  queryCalls.length = 0
  execCalls.length = 0
  queryReturn = []
  vi.clearAllMocks()
})

describe('ensureTables (via first call)', () => {
  it('creates ember_trades with a UNIQUE source_ref and ember_status as a singleton row', async () => {
    await upsertEmberTrade({ sourceRef: 'SPY|2026-10-05', symbol: 'SPY', status: 'open' })
    const ddl = execCalls.join('\n')
    expect(ddl).toContain('CREATE TABLE IF NOT EXISTS ember_trades')
    expect(ddl).toContain('UNIQUE (source_ref)')
    expect(ddl).toContain("strategy TEXT NOT NULL DEFAULT 'reflex'")
    expect(ddl).toContain("ALTER TABLE ember_trades ADD COLUMN IF NOT EXISTS strategy")
    expect(ddl).toContain('CREATE TABLE IF NOT EXISTS ember_status')
    expect(ddl).toContain('id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1)')
  })
})

describe('upsertEmberTrade — idempotent by source_ref', () => {
  it('issues an INSERT ... ON CONFLICT (source_ref) DO UPDATE, never a plain INSERT', async () => {
    await upsertEmberTrade({ sourceRef: 'SPY|2026-10-05', symbol: 'SPY', status: 'open', qty: 10, entryPrice: 12.5 })
    const call = queryCalls.find((c) => c.sql.includes('INSERT INTO ember_trades'))
    expect(call).toBeDefined()
    expect(call!.sql).toContain('ON CONFLICT (source_ref) DO UPDATE SET')
    expect(call!.params).toEqual([null, null, 'SPY', null, 10, 12.5, null, null, 'open', 'reflex', 'SPY|2026-10-05'])
  })

  it('defaults strategy to "reflex" when omitted, but honors an explicit strategy', async () => {
    await upsertEmberTrade({ sourceRef: 'XYZ|2026-10-15', symbol: 'XYZ', status: 'open', strategy: 'cinder' })
    const call = queryCalls.find((c) => c.sql.includes('INSERT INTO ember_trades'))!
    expect(call.params![9]).toBe('cinder')
  })

  it('calling twice with the same source_ref re-states the row through the same upsert path (never a second distinct insert statement)', async () => {
    const trade = { sourceRef: 'SPY|2026-10-05', symbol: 'SPY', status: 'open' as const }
    await upsertEmberTrade(trade)
    await upsertEmberTrade({ ...trade, status: 'closed', pnl: 5.6 })
    const inserts = queryCalls.filter((c) => c.sql.includes('INSERT INTO ember_trades'))
    expect(inserts).toHaveLength(2)
    for (const call of inserts) expect(call.sql).toContain('ON CONFLICT (source_ref) DO UPDATE SET')
    // Same source_ref both times — the DB, not this module, is what collapses
    // them to one row; this asserts the key sent is stable across calls.
    expect(inserts[0].params![10]).toBe('SPY|2026-10-05')
    expect(inserts[1].params![10]).toBe('SPY|2026-10-05')
  })

  it('serializes legs/open_positions as JSON text, not a raw object, for the jsonb column', async () => {
    await upsertEmberTrade({ sourceRef: 'QQQ|2026-10-05', symbol: 'QQQ', status: 'open', legs: { side: 'long' } })
    const call = queryCalls.find((c) => c.sql.includes('INSERT INTO ember_trades'))!
    expect(call.params![3]).toBe(JSON.stringify({ side: 'long' }))
  })
})

describe('getEmberTrades', () => {
  it('orders by opened_at desc and returns whatever rows the DB gives back', async () => {
    queryReturn = [{ id: 1, symbol: 'SPY' }]
    const rows = await getEmberTrades()
    expect(rows).toEqual([{ id: 1, symbol: 'SPY' }])
    const call = queryCalls.find((c) => c.sql.includes('SELECT') && c.sql.includes('FROM ember_trades'))!
    expect(call.sql).toContain('ORDER BY opened_at DESC NULLS LAST')
    expect(call.sql).toContain('strategy')
  })

  it('filters by strategy when one is passed, combined (no WHERE) otherwise', async () => {
    queryReturn = [{ id: 1, symbol: 'XYZ', strategy: 'cinder' }]
    await getEmberTrades(200, 'cinder')
    const call = queryCalls.find((c) => c.sql.includes('SELECT') && c.sql.includes('FROM ember_trades'))!
    expect(call.sql).toContain('WHERE strategy = $1')
    expect(call.params).toEqual(['cinder', 200])
  })
})

describe('ember_status singleton', () => {
  it('upsertEmberStatus always targets id=1 with ON CONFLICT (id) DO UPDATE', async () => {
    await upsertEmberStatus({ state: 'ok', lastHeartbeat: '2026-10-05T19:58:00Z', openPositions: [] })
    const call = queryCalls.find((c) => c.sql.includes('INSERT INTO ember_status'))!
    expect(call.sql).toContain('ON CONFLICT (id) DO UPDATE SET')
    expect(call.params![0]).toBe('ok')
  })

  it('getEmberStatus reads the id=1 row and returns null when no row exists yet', async () => {
    queryReturn = []
    expect(await getEmberStatus()).toBeNull()
    queryReturn = [{ state: 'ok', last_heartbeat: '2026-10-05T19:58:00Z', open_positions: [] }]
    expect(await getEmberStatus()).toEqual({ state: 'ok', last_heartbeat: '2026-10-05T19:58:00Z', open_positions: [] })
  })
})

describe('getEmberEquityCurve — built from ember_trades.pnl, no equity_snapshots table exists', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-15T18:00:00Z')) // 1:00 PM CT, same calendar day as the two "today" rows below
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns an honest empty curve when there are no closed trades at all', async () => {
    queryReturn = []
    expect(await getEmberEquityCurve('all')).toEqual({ points: [], period_pnl: null })
    expect(await getEmberEquityCurve('day')).toEqual({ points: [], period_pnl: null })
  })

  it('filters to one sleeve when a strategy is passed, combined (no strategy predicate) otherwise', async () => {
    queryReturn = [{ id: 1, closed_at: '2026-10-05T15:00:00Z', pnl: '5.00' }]
    await getEmberEquityCurve('all', 'talon')
    const call = queryCalls.find((c) => c.sql.includes('FROM ember_trades'))!
    expect(call.sql).toContain('strategy = $1')
    expect(call.params).toEqual(['talon'])
  })

  it('"all" is the running cumulative sum, period_pnl = the final total', async () => {
    queryReturn = [
      { id: 1, closed_at: '2026-10-01T15:00:00Z', pnl: '10.00' },
      { id: 2, closed_at: '2026-10-05T15:00:00Z', pnl: '-4.00' },
    ]
    const curve = await getEmberEquityCurve('all')
    expect(curve.points).toEqual([
      { timestamp: '2026-10-01T15:00:00Z', cumulative_pnl: 10 },
      { timestamp: '2026-10-05T15:00:00Z', cumulative_pnl: 6 },
    ])
    expect(curve.period_pnl).toBe(6)
  })

  it('"week" drops trades older than the cutoff and rebases period_pnl onto the pre-window baseline', async () => {
    queryReturn = [
      { id: 1, closed_at: '2026-09-01T15:00:00Z', pnl: '100.00' }, // outside the 7-day window -> becomes the baseline
      { id: 2, closed_at: '2026-10-14T15:00:00Z', pnl: '5.00' },
    ]
    const curve = await getEmberEquityCurve('week')
    expect(curve.points[0].cumulative_pnl).toBe(100) // cutoff anchor = baseline, not zero
    expect(curve.points[curve.points.length - 1].cumulative_pnl).toBe(105)
    expect(curve.period_pnl).toBe(5) // only this week's own trade counts, not the pre-existing $100
  })

  it('"week" returns an empty curve (not a flat fabricated line) when nothing closed in the window', async () => {
    queryReturn = [{ id: 1, closed_at: '2026-01-01T15:00:00Z', pnl: '10.00' }]
    const curve = await getEmberEquityCurve('week')
    expect(curve).toEqual({ points: [], period_pnl: null })
  })

  it('"day" anchors on yesterday\'s close and steps through today\'s own trades when some exist', async () => {
    queryReturn = [
      { id: 1, closed_at: '2026-10-14T15:00:00Z', pnl: '50.00' }, // yesterday
      { id: 2, closed_at: '2026-10-15T14:00:00Z', pnl: '3.00' }, // today, 9 AM CT
      { id: 3, closed_at: '2026-10-15T16:00:00Z', pnl: '-1.00' }, // today, 11 AM CT
    ]
    const curve = await getEmberEquityCurve('day')
    // anchor + today's 2 trades = 3 points, anchor sits at yesterday's close of 50
    expect(curve.points).toHaveLength(3)
    expect(curve.points[0].cumulative_pnl).toBe(50)
    expect(curve.points[curve.points.length - 1].cumulative_pnl).toBe(52)
    expect(curve.period_pnl).toBe(2) // +3 - 1, today's own change only
  })

  it('"day" still returns a 2-point line (never a single dot) when nothing closed today yet', async () => {
    queryReturn = [{ id: 1, closed_at: '2026-10-14T15:00:00Z', pnl: '50.00' }]
    const curve = await getEmberEquityCurve('day')
    expect(curve.points).toHaveLength(2)
    expect(curve.points[0].cumulative_pnl).toBe(50)
    expect(curve.points[1].cumulative_pnl).toBe(50)
    expect(curve.period_pnl).toBe(0)
  })
})
