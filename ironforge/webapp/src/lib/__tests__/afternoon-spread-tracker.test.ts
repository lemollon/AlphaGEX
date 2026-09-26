/**
 * DB/Tradier orchestration tests for the "dynamic hedge V2" paper tracker.
 * Trigger math, strike rules, and settlement math are pure and covered in
 * afternoon-spread.test.ts — these tests only exercise:
 *   1. one-trigger-per-side-per-day
 *   2. AFTERNOON_SPREAD_PAPER unset (off) -> nothing is read or written
 *   3. the module imports NO order-placement function, anywhere
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

type Row = Record<string, unknown>

// In-memory tables the mocked `query`/`dbExecute` read and write, so the two
// ticks in the "one trigger per side per day" test see a persistent state,
// the same way the real Postgres table would.
let sessionRows: Row[] = []
let ledgerRows: Row[] = []

const mockQuery = vi.fn(async (sql: string, params: any[] = []) => {
  if (sql.includes('CREATE TABLE')) return []

  if (sql.includes('afternoon_spread_session')) {
    if (sql.startsWith('INSERT')) {
      const [tradeDate, s0, p, c] = params
      if (!sessionRows.some((r) => r.trade_date === tradeDate)) {
        sessionRows.push({ trade_date: tradeDate, s0, p, c })
      }
      return []
    }
    const [tradeDate] = params
    return sessionRows.filter((r) => r.trade_date === tradeDate)
  }

  if (sql.includes('afternoon_spread_ledger')) {
    if (sql.startsWith('INSERT')) {
      const [trade_date, side] = params
      if (!ledgerRows.some((r) => r.trade_date === trade_date && r.side === side)) {
        ledgerRows.push({ trade_date, side })
      }
      return []
    }
    if (sql.includes('SELECT side')) {
      const [tradeDate] = params
      return ledgerRows.filter((r) => r.trade_date === tradeDate)
    }
    return []
  }

  return []
})

const mockDbExecute = vi.fn(async () => 1)

vi.mock('../db', () => ({
  query: (...args: any[]) => (mockQuery as any)(...args),
  dbExecute: (...args: any[]) => (mockDbExecute as any)(...args),
}))

const mockGetQuote = vi.fn()
const mockGetOptionQuote = vi.fn()
const mockGetDailyHistory = vi.fn(async () => [])
const mockBuildOccSymbol = vi.fn(
  (ticker: string, expiration: string, strike: number, type: string) => `${ticker}${expiration}${type}${strike}`,
)

vi.mock('../tradier', () => ({
  getQuote: (...args: any[]) => (mockGetQuote as any)(...args),
  getOptionQuote: (...args: any[]) => (mockGetOptionQuote as any)(...args),
  getDailyHistory: (...args: any[]) => (mockGetDailyHistory as any)(...args),
  buildOccSymbol: (...args: any[]) => (mockBuildOccSymbol as any)(...args),
}))

// The tracker dynamically imports scanner.ts ONLY to read FLAME's own VIX
// gate ratio (see readFlameVixRatio) — mocked here so the real scanner.ts
// (which pulls in a huge amount of its own DB/Tradier surface) is never
// loaded by this test file at all.
vi.mock('../scanner', () => ({
  vixDecayCheck: vi.fn().mockResolvedValue({ reason: null, ratio: 0.5, prior: 12, windowMax: 24 }),
  VIX_DECAY_CEILING: { spark: 0.90, flame: 0.80 },
}))

// Local-time constructor (not Date.UTC): the tracker reads ct.getHours()/
// getMinutes() exactly like scanner.ts's own ctHHMM(ct) does, so a test date
// must be built the same way — Date.UTC would only round-trip correctly
// through .getHours() on a machine whose local TZ is itself UTC.
function ctAt(hh: number, mm: number): Date {
  return new Date(2026, 8, 26, hh, mm, 0)
}

beforeEach(() => {
  sessionRows = []
  ledgerRows = []
  mockQuery.mockClear()
  mockDbExecute.mockClear()
  mockGetQuote.mockReset()
  mockGetOptionQuote.mockReset()
  delete process.env.AFTERNOON_SPREAD_PAPER
})

describe('AFTERNOON_SPREAD_PAPER off -> nothing read or written', () => {
  it('runAfternoonSpreadTick no-ops with the flag unset', async () => {
    const { runAfternoonSpreadTick } = await import('../afternoon-spread-tracker')
    const result = await runAfternoonSpreadTick(ctAt(13, 20))
    expect(result).toBe('')
    expect(mockQuery).not.toHaveBeenCalled()
    expect(mockDbExecute).not.toHaveBeenCalled()
    expect(mockGetQuote).not.toHaveBeenCalled()
  })

  it('settleAfternoonSpreadExpired no-ops with the flag unset', async () => {
    const { settleAfternoonSpreadExpired } = await import('../afternoon-spread-tracker')
    const result = await settleAfternoonSpreadExpired(ctAt(15, 5))
    expect(result).toBe('')
    expect(mockQuery).not.toHaveBeenCalled()
    expect(mockDbExecute).not.toHaveBeenCalled()
  })

  it('every value other than exactly "on" is off', async () => {
    const { runAfternoonSpreadTick } = await import('../afternoon-spread-tracker')
    for (const v of ['off', '', 'true', '1', 'ON ']) {
      process.env.AFTERNOON_SPREAD_PAPER = v
      mockQuery.mockClear()
      const result = await runAfternoonSpreadTick(ctAt(13, 20))
      expect(result, `"${v}" must not trade`).toBe('')
    }
  })
})

describe('one trigger per side per day', () => {
  beforeEach(() => {
    process.env.AFTERNOON_SPREAD_PAPER = 'on'
  })

  it('captures S0 once, fires down_call once, and never re-fires it later the same day', async () => {
    const { runAfternoonSpreadTick } = await import('../afternoon-spread-tracker')

    // Tick 1, 13:20 CT: S0 capture (582) -> P=581, C=583. Current spot for the
    // trigger check comes back lower (581.2), inside the $0.50 down-trigger band.
    mockGetQuote
      .mockResolvedValueOnce({ last: 582 }) // S0 capture
      .mockResolvedValueOnce({ last: 581.2 }) // current spot for the trigger check
    mockGetOptionQuote
      .mockResolvedValueOnce({ bid: 0.30, ask: 0.35 }) // short call
      .mockResolvedValueOnce({ bid: 0.05, ask: 0.10 }) // long call

    const first = await runAfternoonSpreadTick(ctAt(13, 20))
    expect(first).toContain('down_call=tracked')
    expect(mockGetOptionQuote).toHaveBeenCalledTimes(2)
    expect(ledgerRows).toHaveLength(1)
    expect(ledgerRows[0]).toMatchObject({ side: 'down_call' })

    // Tick 2, same day, 13:21 CT: session already captured (no new getQuote
    // call for S0), spot is STILL inside the down-trigger band — but the
    // side already fired today, so it must not re-fire or read another
    // option quote.
    mockGetOptionQuote.mockClear()
    mockGetQuote.mockReset().mockResolvedValueOnce({ last: 581.1 })

    const second = await runAfternoonSpreadTick(ctAt(13, 21))
    expect(second).toBe('')
    expect(mockGetOptionQuote).not.toHaveBeenCalled()
    expect(ledgerRows).toHaveLength(1) // still just the one row from tick 1
  })

  it('does not evaluate triggers before 13:05 CT, and does not fire outside the 13:10-14:45 window', async () => {
    const { runAfternoonSpreadTick } = await import('../afternoon-spread-tracker')

    const before = await runAfternoonSpreadTick(ctAt(12, 59))
    expect(before).toBe('')
    expect(mockGetQuote).not.toHaveBeenCalled()

    // 13:07 CT: inside the S0-capture minute range but before the 13:10
    // trigger window opens — S0 gets captured, but no trigger is evaluated.
    mockGetQuote.mockResolvedValueOnce({ last: 582 })
    const duringCapture = await runAfternoonSpreadTick(ctAt(13, 7))
    expect(duringCapture).toBe('')
    expect(sessionRows).toHaveLength(1)
    expect(mockGetOptionQuote).not.toHaveBeenCalled()
  })
})

/** Strip /** ... *\/ and // comments so a doc comment that NAMES a forbidden function (to document its absence) can't itself trip the substring check. */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')
}

describe('imports no order-placement function', () => {
  const trackerSource = stripComments(readFileSync(
    resolve(__dirname, '../afternoon-spread-tracker.ts'),
    'utf-8',
  ))
  const pureSource = stripComments(readFileSync(
    resolve(__dirname, '../afternoon-spread.ts'),
    'utf-8',
  ))
  // Import-statement checks below need the ORIGINAL (commented) source —
  // re-read it separately rather than reusing the stripped copy.
  const trackerSourceRaw = readFileSync(resolve(__dirname, '../afternoon-spread-tracker.ts'), 'utf-8')

  // Every function in tradier.ts that places, cancels, or closes a real
  // broker order or position. Mirrors the safety proof PR #3074 gave for
  // blaze/flare's paper executors, as a static assertion instead of a
  // written claim.
  const ORDER_FUNCTIONS = [
    'placeHedgePutSpread',
    'placeIcOrderAllAccounts',
    'placeCallSpreadOrderAllAccounts',
    'closeIcOrderAllAccounts',
    'cancelSandboxOrder',
    'emergencyCloseSandboxPositions',
    'closeOrphanSandboxPositions',
    'closeAllSandboxPositions',
    'resolveEligibleAccounts',
    'canPlaceLiveOrders',
  ]

  it('afternoon-spread-tracker.ts never references an order function', () => {
    for (const fn of ORDER_FUNCTIONS) {
      expect(trackerSource.includes(fn), `tracker must not reference ${fn}`).toBe(false)
    }
  })

  it('afternoon-spread.ts (pure module) never references an order function', () => {
    for (const fn of ORDER_FUNCTIONS) {
      expect(pureSource.includes(fn), `pure module must not reference ${fn}`).toBe(false)
    }
  })

  it("only imports the read-only allowlist from '../tradier'", () => {
    const match = trackerSourceRaw.match(/import\s*\{([^}]+)\}\s*from\s*'\.\/tradier'/)
    expect(match, "expected a named import from './tradier'").not.toBeNull()
    const imported = match![1].split(',').map((s) => s.trim()).filter(Boolean)
    const ALLOWED = ['getQuote', 'getOptionQuote', 'buildOccSymbol', 'getDailyHistory']
    for (const name of imported) {
      expect(ALLOWED, `tradier import "${name}" is not on the read-only allowlist`).toContain(name)
    }
  })

  it('only has static imports from ./tradier, ./db, and ./afternoon-spread', () => {
    const staticImports = [...trackerSourceRaw.matchAll(/^import\s*\{[^}]*\}\s*from\s*'([^']+)'/gm)].map((m) => m[1])
    expect(staticImports.length).toBe(3)
    for (const spec of staticImports) {
      expect(['./tradier', './db', './afternoon-spread'], `unexpected static import: ${spec}`).toContain(spec)
    }
  })

  it('the only dynamic import is scanner.ts, read for the VIX ratio only', () => {
    const dynamicImports = [...trackerSourceRaw.matchAll(/await import\('([^']+)'\)/g)].map((m) => m[1])
    expect(dynamicImports).toEqual(['./scanner'])
  })
})
