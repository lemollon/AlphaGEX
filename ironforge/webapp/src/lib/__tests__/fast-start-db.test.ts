/**
 * fast-start-db.ts — updateFastStartEodState, the ONE place phase/
 * peak_profit ever change (2026-09-29 correction: EOD-only, from closing
 * equity, never intraday). Mocks ../db the same way fast-start-wiring.test.ts
 * does.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockDbQuery = vi.fn()
const mockDbExecute = vi.fn().mockResolvedValue(1)

let stateStore: Record<string, { phase: number; deposit: number; peak_profit: number; last_eod_date: string | null }> = {}

vi.mock('../db', () => ({
  query: (...args: any[]) => mockDbQuery(...args),
  dbExecute: (...args: any[]) => mockDbExecute(...args),
  botTable: (bot: string, table: string) => `${bot}_${table}`,
}))
// flint.ts pulls in scanner-adjacent modules; stub the one function this file imports.
vi.mock('../flint', () => ({ flintMaxLoss: (s: number, l: number, c: number, n: number) => (l - s - c) * 100 * n + 1.4 * n }))

beforeEach(() => {
  stateStore = {}
  mockDbQuery.mockReset()
  mockDbExecute.mockReset().mockResolvedValue(1)
  mockDbQuery.mockImplementation(async (sql: string, params: any[] = []) => {
    if (sql.includes('SELECT phase, deposit, peak_profit, last_eod_date FROM fast_start_state')) {
      const key = `${params[0]}:${params[1]}`
      return stateStore[key] ? [stateStore[key]] : []
    }
    if (sql.includes('UPDATE fast_start_state')) {
      const key = `${params[0]}:${params[1]}`
      if (stateStore[key]) {
        stateStore[key].peak_profit = params[2]
        stateStore[key].phase = params[3]
        stateStore[key].last_eod_date = params[4]
      }
      return []
    }
    return []
  })
})

import { updateFastStartEodState } from '../fast-start-db'

describe('updateFastStartEodState', () => {
  it('no state row yet -> no-op, reason=no_state_row_yet', async () => {
    const r = await updateFastStartEodState('User', 'sandbox', '2026-09-29', 5000, 2, true, 170, false, null)
    expect(r.updated).toBe(false)
    expect(r.reason).toBe('no_state_row_yet')
  })

  it('idempotent: a second call the SAME trade_date is a no-op', async () => {
    stateStore['User:sandbox'] = { phase: 1, deposit: 4242, peak_profit: 0, last_eod_date: '2026-09-29' }
    const r = await updateFastStartEodState('User', 'sandbox', '2026-09-29', 5000, 2, true, 170, false, null)
    expect(r.updated).toBe(false)
    expect(r.reason).toBe('already_updated_today')
  })

  it('ratchets peak_profit from closing equity, never decreases it', async () => {
    stateStore['User:sandbox'] = { phase: 2, deposit: 4242, peak_profit: 500, last_eod_date: '2026-09-28' }
    // closingEquity=4600 -> cushion=358 < prior peak_profit(500) -> ratchet keeps 500.
    const r1 = await updateFastStartEodState('User', 'sandbox', '2026-09-29', 4600, 3, true, 170, false, null)
    expect(r1.peakProfit).toBe(500)
    stateStore['User:sandbox'].last_eod_date = '2026-09-29'
    // next day, closingEquity=6000 -> cushion=1758 > 500 -> ratchets up.
    const r2 = await updateFastStartEodState('User', 'sandbox', '2026-09-30', 6000, 3, true, 170, false, null)
    expect(r2.peakProfit).toBe(1758)
  })

  it('advances phase 1 -> 2 when the trigger clears using CLOSING equity', async () => {
    stateStore['User:sandbox'] = { phase: 1, deposit: 2000, peak_profit: 0, last_eod_date: '2026-09-28' }
    // ladder=1, ebb_ml=170, flint not candidate -> combined=170. trigger=8*170=1360.
    // closingEquity=3400 -> cushion=1400 >= 1360 -> triggers.
    const r = await updateFastStartEodState('User', 'sandbox', '2026-09-29', 3400, 1, true, 170, false, null)
    expect(r.triggeredToday).toBe(true)
    expect(r.phase).toBe(2)
  })

  it('does NOT advance when the trigger does not clear', async () => {
    stateStore['User:sandbox'] = { phase: 1, deposit: 2000, peak_profit: 0, last_eod_date: '2026-09-28' }
    const r = await updateFastStartEodState('User', 'sandbox', '2026-09-29', 2100, 1, true, 170, false, null)
    expect(r.triggeredToday).toBe(false)
    expect(r.phase).toBe(1)
  })

  it('phase 2 never re-evaluates the trigger (sticky, one-way)', async () => {
    stateStore['User:sandbox'] = { phase: 2, deposit: 2000, peak_profit: 5000, last_eod_date: '2026-09-28' }
    const r = await updateFastStartEodState('User', 'sandbox', '2026-09-29', 100, 1, true, 170, false, null)
    expect(r.phase).toBe(2)
    expect(r.triggeredToday).toBe(false)
  })

  it('unreadable deposit/equity -> fails closed, no write', async () => {
    stateStore['User:sandbox'] = { phase: 1, deposit: 2000, peak_profit: 0, last_eod_date: '2026-09-28' }
    const r = await updateFastStartEodState('User', 'sandbox', '2026-09-29', NaN, 1, true, 170, false, null)
    expect(r.updated).toBe(false)
    expect(r.reason).toBe('deposit_or_equity_unreadable')
  })

  it('2026-10-10 regression: the UPDATE never reuses one placeholder across two different inferred types', async () => {
    // The real bug this guards: `phase = $4 ... WHEN $4 = 2` made Postgres
    // reject the query with "inconsistent types deduced for parameter $4"
    // on every single call in production (confirmed in Render logs, firing
    // every minute for Logan's SPARK sandbox state) -- a mock can't replicate
    // Postgres's own type inference, so assert the query text directly: no
    // placeholder may appear in both a column assignment and a bare `= <int
    // literal>` comparison, and triggeredToday is passed as its own param.
    stateStore['User:sandbox'] = { phase: 1, deposit: 2000, peak_profit: 0, last_eod_date: '2026-09-28' }
    await updateFastStartEodState('User', 'sandbox', '2026-09-29', 3400, 1, true, 170, false, null)
    const updateCall = mockDbQuery.mock.calls.find(([sql]) => sql.includes('UPDATE fast_start_state'))
    expect(updateCall).toBeDefined()
    const [sql, params] = updateCall!
    expect(sql).not.toMatch(/\$4\s*=\s*2/)
    expect(params).toContain(true) // triggeredToday, its own parameter
  })
})
