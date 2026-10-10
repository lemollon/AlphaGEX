/**
 * EMBER trade book — pins the upsert-by-source_ref idempotency contract
 * (ON CONFLICT (source_ref) DO UPDATE, never a second INSERT path) and the
 * read shapes the API routes depend on. Mocks ../db the same way
 * calldiag-tracker.test.ts does.
 */
import { describe, it, expect, afterEach, vi } from 'vitest'

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
    expect(call!.params).toEqual([null, null, 'SPY', null, 10, 12.5, null, null, 'open', 'SPY|2026-10-05'])
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
    expect(inserts[0].params![9]).toBe('SPY|2026-10-05')
    expect(inserts[1].params![9]).toBe('SPY|2026-10-05')
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
