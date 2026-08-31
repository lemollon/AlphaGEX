import { describe, it, expect, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { canPlaceLiveOrders, isFlameLiveArmed } from '../tradier'

/**
 * A PAPER FILL MUST NOT CONSUME THE LIVE ACCOUNT'S ENTRY ATTEMPT.
 *
 * 2026-08-31: FLAME picked SPY 764/766P at 13:05 CT. The pre-order buying-power
 * read came back null (Tradier's /balances was failing roughly two calls in
 * three that afternoon), the live order was abandoned, and the paper book opened
 * the trade anyway. FLAME's live entry window is 13:05-13:10 CT, so four scan
 * cycles remained — and not one of them re-attempted the live order, because
 * both entry counters (`tradedTodayCount`, `hasBlockingOpenPosition`) count
 * SANDBOX rows and the paper fill had already closed the gate.
 *
 * The scanner's local isProductionBot() is SPARK + KINDLE only, so the
 * production-only catch-up path that was supposed to cover exactly this never
 * applied to FLAME, despite an in-code comment claiming it did.
 *
 * These tests pin the two halves of the fix:
 *   1. the predicate — canPlaceLiveOrders is the one that means "places real
 *      orders today", and it is FLAME-when-armed and never SPARK;
 *   2. the wiring — the scanner's entry gate consults it, and does so only when
 *      the live account genuinely holds nothing today.
 *
 * The wiring half asserts on scanner source text on purpose. The gate is an
 * inline boolean deep inside a multi-hundred-line scan function with live DB
 * calls either side of it; re-implementing that expression in a test would pin a
 * copy rather than the code that runs. Asserting the real file still contains
 * the guard catches the regression that actually matters — someone simplifying
 * the condition back out.
 */

const ENV_KEYS = ['IRONFORGE_FLAME_LIVE', 'TRADIER_FLAME_API_KEY', 'TRADIER_FLAME_ACCOUNT_ID'] as const

const ARMED = {
  IRONFORGE_FLAME_LIVE: 'true',
  TRADIER_FLAME_API_KEY: 'test-key',
  TRADIER_FLAME_ACCOUNT_ID: 'test-account',
} as const

function setEnv(vars: Record<string, string>) {
  for (const k of ENV_KEYS) delete process.env[k]
  Object.assign(process.env, vars)
}

afterEach(() => {
  for (const k of ENV_KEYS) delete process.env[k]
})

const SCANNER_SRC = readFileSync(join(__dirname, '..', 'scanner.ts'), 'utf8')

describe('the predicate that decides who may catch up live', () => {
  it('is true for FLAME only while armed', () => {
    setEnv(ARMED)
    expect(isFlameLiveArmed()).toBe(true)
    expect(canPlaceLiveOrders('flame')).toBe(true)

    setEnv({})
    expect(canPlaceLiveOrders('flame')).toBe(false)
  })

  it('is never true for SPARK, armed or not — SPARK is paper-only', () => {
    setEnv(ARMED)
    expect(canPlaceLiveOrders('spark')).toBe(false)
    setEnv({})
    expect(canPlaceLiveOrders('spark')).toBe(false)
  })

  it('is false for a bot with no live path at all', () => {
    setEnv(ARMED)
    expect(canPlaceLiveOrders('inferno')).toBe(false)
  })
})

describe('the scanner entry gate re-attempts the live order', () => {
  it('feeds liveStillNeedsEntry into canOpenMore', () => {
    const gate = SCANNER_SRC.slice(SCANNER_SRC.indexOf('const canOpenMore ='))
      .slice(0, 400)
    expect(gate).toContain('liveStillNeedsEntry')
  })

  it('decides liveStillNeedsEntry from canPlaceLiveOrders, not isProductionBot', () => {
    expect(SCANNER_SRC).toContain('if (canPlaceLiveOrders(bot.name) && prodOpenRows.length === 0)')
  })

  it('only opens the gate when production opened nothing today', () => {
    const block = SCANNER_SRC.slice(SCANNER_SRC.indexOf('let liveStillNeedsEntry = false'))
      .slice(0, 900)
    // Both halves must be present: no live position open right now, AND none
    // opened earlier today. Dropping either one turns this into a second live order.
    expect(block).toContain('prodOpenRows.length === 0')
    expect(block).toContain("account_type = 'production'")
    expect(block).toContain('CT_TODAY')
  })

  it('fails closed — a failed lookup must not permit a live order', () => {
    const block = SCANNER_SRC.slice(SCANNER_SRC.indexOf('let liveStillNeedsEntry = false'))
      .slice(0, 900)
    // The flag is initialised false and only ever set from a successful COUNT.
    expect(block).toMatch(/let liveStillNeedsEntry = false/)
    expect(block).toMatch(/catch \{[^}]*\}/)
    expect(block).not.toContain('liveStillNeedsEntry = true')
  })

  it('lets a live-armed bot reach production-only mode in tryOpenTrade', () => {
    expect(SCANNER_SRC).toContain('if (isProductionBot(bot.name) || canPlaceLiveOrders(bot.name)) {')
  })

  it('still places with productionOnly so the paper book is not re-opened', () => {
    const branch = SCANNER_SRC.slice(SCANNER_SRC.indexOf('if (sandboxAlreadyTraded) {'))
      .slice(0, 1600)
    expect(branch).toContain('productionOnly: true')
  })
})
