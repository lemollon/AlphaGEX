/**
 * CALLDIAG tracker — pins that CALLDIAG_MODE unset means ZERO DB or Tradier
 * calls (not just an empty return string), and that both ticks are no-ops
 * outside their own entry/exit clock windows even when armed. Mirrors the
 * mock style flint-multi-account.test.ts already uses for tradier.ts/db.ts.
 */
import { describe, it, expect, afterEach, vi } from 'vitest'

const dbCalls: string[] = []
const tradierCalls: string[] = []

vi.mock('../db', () => ({
  query: vi.fn(async (sql: string) => {
    dbCalls.push(sql)
    return []
  }),
  dbExecute: vi.fn(async (sql: string) => {
    dbCalls.push(sql)
  }),
}))

vi.mock('../tradier', () => ({
  getOptionExpirations: vi.fn(async () => {
    tradierCalls.push('getOptionExpirations')
    return []
  }),
  getOptionChainQuotes: vi.fn(async () => {
    tradierCalls.push('getOptionChainQuotes')
    return []
  }),
  getOptionQuote: vi.fn(async () => {
    tradierCalls.push('getOptionQuote')
    return null
  }),
  buildOccSymbol: (t: string, e: string, k: number, cp: string) => `${t}${e}${cp}${k}`,
  getDailyHistory: vi.fn(async () => {
    tradierCalls.push('getDailyHistory')
    return []
  }),
  resolveEligibleAccounts: vi.fn(async () => {
    tradierCalls.push('resolveEligibleAccounts')
    return []
  }),
  getAllocatedCapitalForAccount: vi.fn(async () => null),
  getProductionLadderCapital: vi.fn(async () => null),
  getOrSeedFlintAccountFloor: vi.fn(async () => null),
}))

import { runCallDiagEntryTick, runCallDiagExitTick } from '../calldiag-tracker'

afterEach(() => {
  delete process.env.CALLDIAG_MODE
  dbCalls.length = 0
  tradierCalls.length = 0
})

function ctAt(hh: number, mm: number): Date {
  const d = new Date()
  d.setHours(hh, mm, 0, 0)
  return d
}

describe('CALLDIAG_MODE unset — zero DB/Tradier calls, on either tick', () => {
  it('entry tick: no-op, touches nothing', async () => {
    delete process.env.CALLDIAG_MODE
    const result = await runCallDiagEntryTick(ctAt(8, 36))
    expect(result).toBe('')
    expect(dbCalls).toEqual([])
    expect(tradierCalls).toEqual([])
  })
  it('exit tick: no-op, touches nothing', async () => {
    delete process.env.CALLDIAG_MODE
    const result = await runCallDiagExitTick(ctAt(14, 59))
    expect(result).toBe('')
    expect(dbCalls).toEqual([])
    expect(tradierCalls).toEqual([])
  })
})

describe('window gating — armed but outside the entry/exit clock', () => {
  it('entry tick no-ops before 08:35 CT / after 08:39 CT even when mode=paper', async () => {
    process.env.CALLDIAG_MODE = 'paper'
    expect(await runCallDiagEntryTick(ctAt(8, 34))).toBe('')
    expect(await runCallDiagEntryTick(ctAt(8, 40))).toBe('')
    expect(dbCalls).toEqual([])
    expect(tradierCalls).toEqual([])
  })
  it('exit tick no-ops before 14:59 CT even when mode=paper', async () => {
    process.env.CALLDIAG_MODE = 'paper'
    expect(await runCallDiagExitTick(ctAt(14, 58))).toBe('')
    expect(dbCalls).toEqual([])
    expect(tradierCalls).toEqual([])
  })
})
