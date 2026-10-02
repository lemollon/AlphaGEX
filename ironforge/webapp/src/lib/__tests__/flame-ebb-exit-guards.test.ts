/**
 * 2026-10-02 audit fixes (FLAME-SPY-20261002-Y7RZKZ, -$32 early close):
 *  1. EBB settle-at-expiry bots never take an intraday profit target, even when a
 *     DB config row overrides pt_pct below 1.0.
 *  2. The FLAME v2 call spread only runs when the SPY put book opened today.
 *  3. A failed CALM seed load retries instead of being disabled for the process.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

const SCANNER_SRC = readFileSync(join(__dirname, '..', 'scanner.ts'), 'utf8')

describe('EBB profit-target guard', () => {
  it('returns HOLD_TO_EOD for settle-at-expiry bots before reading basePt', () => {
    const fn = SCANNER_SRC.slice(SCANNER_SRC.indexOf('function getSlidingProfitTarget('))
    const guard = fn.indexOf("if (isSettleAtExpiryBot(botName)) return [1.0, 'HOLD_TO_EOD']")
    const baseCheck = fn.indexOf("if (basePt >= 1.0) return [1.0, 'HOLD_TO_EOD']")
    expect(guard).toBeGreaterThan(0)
    expect(guard).toBeLessThan(baseCheck)
  })
})

describe('FLAME v2 call spread mirrors the put', () => {
  it('gates runFlameV2CallSpreadEntryTick on the SPY put having opened today', () => {
    expect(SCANNER_SRC).toContain("spyPutResult.startsWith('SPY=traded@') || spyPutResult === 'SPY=traded_today'")
    const gate = SCANNER_SRC.indexOf("if (bot.name === 'flame' && putOpenedToday) {")
    const call = SCANNER_SRC.indexOf('await runFlameV2CallSpreadEntryTick(')
    expect(gate).toBeGreaterThan(0)
    expect(call).toBeGreaterThan(gate)
  })
})

const dbExecute = vi.fn()
vi.mock('@/lib/db', () => ({ query: vi.fn().mockResolvedValue([]), dbExecute: (...a: any[]) => dbExecute(...a) }))

describe('ensureCalmSeedLoaded retry', () => {
  beforeEach(() => { dbExecute.mockReset(); vi.useFakeTimers() })

  it('retries after a failure instead of disabling CALM for the process', async () => {
    const { ensureCalmSeedLoaded } = await import('../flame-v2/signal-store')
    vi.setSystemTime(new Date('2026-10-05T14:00:00Z'))
    // table ensure ok, first chunk insert fails
    dbExecute.mockImplementation(async (sql: string) => {
      if (sql.includes('INSERT INTO flame_v2_signal_history')) throw new Error('cold start')
      return 0
    })
    await ensureCalmSeedLoaded('flame')
    const failedInserts = dbExecute.mock.calls.filter(c => String(c[0]).includes('INSERT')).length
    expect(failedInserts).toBe(1)

    // within the retry window: no new attempt
    await ensureCalmSeedLoaded('flame')
    expect(dbExecute.mock.calls.filter(c => String(c[0]).includes('INSERT')).length).toBe(1)

    // after the window: retries and succeeds
    dbExecute.mockImplementation(async () => 1)
    vi.setSystemTime(new Date('2026-10-05T14:11:00Z'))
    await ensureCalmSeedLoaded('flame')
    const after = dbExecute.mock.calls.filter(c => String(c[0]).includes('INSERT')).length
    expect(after).toBeGreaterThan(1)

    // loaded: no further inserts even after the window
    vi.setSystemTime(new Date('2026-10-05T15:00:00Z'))
    await ensureCalmSeedLoaded('flame')
    expect(dbExecute.mock.calls.filter(c => String(c[0]).includes('INSERT')).length).toBe(after)
  })
})

describe('EBB DB exit override is ignored', () => {
  it('both config loaders pin pt/sl for settle-at-expiry bots after the DB merge', () => {
    const calls = SCANNER_SRC.split('pinEbbExitConfig(bot.name, merged)').length - 1
    expect(calls).toBe(2)
    const fn = SCANNER_SRC.slice(SCANNER_SRC.indexOf('function pinEbbExitConfig('))
    expect(fn).toContain('if (!isSettleAtExpiryBot(botName)) return')
    expect(fn).toContain('merged.pt_pct = d.pt_pct')
    expect(fn).toContain('merged.sl_mult = d.sl_mult')
  })
})

describe('closeAllSandboxPositions is sandbox-only', () => {
  it('refuses a non-sandbox baseUrl before touching the broker', async () => {
    const { closeAllSandboxPositions } = await import('../tradier')
    const f = vi.fn(); vi.stubGlobal('fetch', f)
    expect(await closeAllSandboxPositions('k', 'https://api.tradier.com/v1')).toBe(0)
    expect(f).not.toHaveBeenCalled()
  })
})

const TRADIER_SRC = readFileSync(join(__dirname, '..', 'tradier.ts'), 'utf8')

describe('hold-to-expiry lock', () => {
  it('closePosition blocks FLAME/SPARK broker closes before the guard window, except guard/settlement/stale', () => {
    const fn = SCANNER_SRC.slice(SCANNER_SRC.indexOf('async function closePosition('))
    const lock = fn.indexOf('EARLY CLOSE BLOCKED')
    const broker = fn.indexOf('closeIcOrderAllAccounts(')
    expect(lock).toBeGreaterThan(0)
    expect(lock).toBeLessThan(broker)
    expect(fn).toContain("if (isSettleAtExpiryBot(bot.name) && reason !== ASSIGNMENT_GUARD_REASON")
    expect(fn).toContain("&& !isBookOnlyCloseReason(reason) && reason !== 'stale_holdover')")
    expect(fn).toContain('if (hhmm < startHHMM) {')
  })
})

describe('price-capped close never degrades to market', () => {
  it('returns before the market Stage 2/3 fallback when the order type is debit', () => {
    const fn = TRADIER_SRC.slice(TRADIER_SRC.indexOf('export async function closeIcOrderAllAccounts('))
    const guard = fn.indexOf("if (effectiveOrderType === 'debit') {")
    const stage2 = fn.indexOf('// --- Stage 2: 2 × 2-leg spread close ---')
    expect(guard).toBeGreaterThan(0)
    expect(guard).toBeLessThan(stage2)
  })
})

describe('settlement books the broker fill when the broker closed early', () => {
  it('settleExpiredPositions consults productionSpreadCloseFill for production rows before booking', () => {
    const fn = SCANNER_SRC.slice(SCANNER_SRC.indexOf('async function settleExpiredPositions('))
    const check = fn.indexOf('productionSpreadCloseFill(')
    const book = fn.indexOf("'settled_at_expiry', value,")
    expect(check).toBeGreaterThan(0)
    expect(check).toBeLessThan(book)
  })
})

describe('EBB entry window is code-controlled', () => {
  it('pins entry_start/entry_end after the DB entry_end string is parsed, in both loaders', () => {
    const fn = SCANNER_SRC.slice(SCANNER_SRC.indexOf('function pinEbbExitConfig('))
    expect(fn).toContain('merged.entry_start = d.entry_start')
    expect(fn).toContain('merged.entry_end = d.entry_end')
    expect(fn).toContain('merged.starting_capital = d.starting_capital')
    for (const loader of ['async function loadConfigOverrides(', 'async function loadProductionConfigFor(']) {
      const i = SCANNER_SRC.indexOf(loader)
      if (i < 0) continue
      const body = SCANNER_SRC.slice(i, i + 6000)
      const parse = body.indexOf('merged.entry_end = h * 100 + m')
      const pin = body.indexOf('pinEbbExitConfig(bot.name, merged)')
      expect(parse).toBeGreaterThan(0)
      expect(pin).toBeGreaterThan(parse)
    }
  })
})
