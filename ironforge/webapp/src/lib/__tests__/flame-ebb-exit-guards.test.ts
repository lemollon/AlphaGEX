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
