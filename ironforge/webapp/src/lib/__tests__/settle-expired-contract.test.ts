import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

/**
 * AN EXPIRED CONTRACT HAS NO MARKET, AND A SETTLEMENT MUST NEVER WAIT FOR A FILL.
 *
 * SPARK's 8/21, 8/24 and 8/25 positions were still `status = open` on 8/26. Every
 * 60s scan cycle the settle path called closePosition, which mirrored the close to
 * Tradier — against contracts that had already expired. Tradier rejected all of
 * them ("There is no price. Security symbol: SPY260824P00762000"), so `fill_price`
 * never arrived, closePosition took the DEFER branch and returned without flipping
 * `status`, and the caller logged "SETTLED ... pnl=$35.00" anyway. Three days of
 * confident settlement lines for settlements that never happened, ~9 rejected
 * multileg orders a minute, and — with max 1 concurrent position — every SPARK
 * entry blocked from 8/21 onward.
 *
 * Two independent defects, so two independent pins:
 *   1. Do not send a close order to a broker for a contract that has expired.
 *   2. Do not log an outcome you have not read back out of the database.
 */

const SRC = readFileSync(join(__dirname, '..', 'scanner.ts'), 'utf8')

/** The predicate closePosition uses to recognise a contract with no market. */
function isExpiredContract(reason: string, expiration: unknown, todayCT: string): boolean {
  const d = expiration as { toISOString?: () => string }
  const exp = d?.toISOString?.()?.slice(0, 10) || String(expiration).slice(0, 10)
  return reason === 'settled_at_expiry' || exp < todayCT
}

describe('expired contracts are settled on the books, never at the broker', () => {
  it('treats a settlement as expired whatever the date says', () => {
    expect(isExpiredContract('settled_at_expiry', '2026-08-26', '2026-08-26')).toBe(true)
  })

  it('treats any past-dated contract as expired', () => {
    // The three positions that actually stuck.
    expect(isExpiredContract('profit_target_MORNING', '2026-08-21', '2026-08-26')).toBe(true)
    expect(isExpiredContract('profit_target_MORNING', '2026-08-24', '2026-08-26')).toBe(true)
    expect(isExpiredContract('eod_close', '2026-08-25', '2026-08-26')).toBe(true)
  })

  it('reads a pg DATE the same way, so a Date does not fall through as live', () => {
    expect(isExpiredContract('eod_close', new Date('2026-08-24T00:00:00Z'), '2026-08-26')).toBe(true)
  })

  it('leaves a live contract alone — it still closes at the broker', () => {
    expect(isExpiredContract('profit_target_MORNING', '2026-08-26', '2026-08-26')).toBe(false)
    expect(isExpiredContract('stop_loss', '2026-08-27', '2026-08-26')).toBe(false)
  })

  it('skips the broker mirror for an expired contract', () => {
    expect(SRC).toMatch(/shouldCloseSandbox = isProductionBotClose && !isExpiredContract/)
  })

  it('never lets an expired contract reach either DEFER branch', () => {
    // Both defers keep the position open waiting for a fill that cannot come.
    expect(SRC).toMatch(
      /isProductionBotClose && !isExpiredContract && userClose\?\.order_id && userClose\.order_id > 0/,
    )
    expect(SRC).toMatch(/\} else if \(isProductionBotClose && !isExpiredContract\) \{/)
  })
})

describe('SETTLED is logged only after the row actually moves', () => {
  it('closePosition reports WHAT HAPPENED, not a boolean', () => {
    // Upgraded 2026-08-26. A boolean collapsed two different things: a genuine
    // failure and a legitimate DEFERRAL (limit order live, fill pending — the normal
    // path for FLAME's debit-limit profit-target exit). Callers could not tell them
    // apart, so they ignored the result and announced `closed:` regardless.
    expect(SRC).toMatch(/limitPrice\?: number,\s*\): Promise<CloseOutcome> \{/)
  })

  it('every early return out of closePosition names an outcome', () => {
    // A bare `return` here is the original bug: the caller reads it as success.
    const body = SRC.slice(
      SRC.indexOf('async function closePosition('),
      SRC.indexOf('/*  FLAME — Bull Put Credit Spread entry'),
    )
    expect(body.length).toBeGreaterThan(1000)
    expect(body).not.toMatch(/\n\s*return\s*(\/\/[^\n]*)?\n/)
    expect(body).not.toMatch(/return (true|false)\b/)
    // The order is live and the fill is coming — NOT a failure.
    expect(body).toMatch(/return 'deferred' \/\/ Exit without closing paper/)
    // The broker refused outright.
    expect(body).toMatch(/return 'failed' \/\/ do NOT book the paper close/)
    // A 0-row UPDATE is a failure, never a quiet success.
    expect(body).toMatch(/return 'failed'\n  \}/)
    expect(body).toMatch(/\n  return 'closed'\n\}/)
  })

  it('the settle path branches on that result instead of assuming it', () => {
    expect(SRC).toMatch(/const settleOutcome = await closePosition\(/)
    // Only 'closed' is a settlement. 'deferred' is not success by omission.
    expect(SRC).toMatch(/const settled = settleOutcome === 'closed'/)
    expect(SRC).toMatch(/if \(!settled\) \{/)
    expect(SRC).toMatch(/SETTLE DID NOT CLOSE/)
    expect(SRC).toMatch(/=settle_declined/)
  })

  it('a declined settle is written where a human will see it', () => {
    // A console.warn goes to Render only; the scan `reason` is overwritten later
    // in the cycle. The bot's own log table is the surface that survives.
    const declined = SRC.slice(SRC.indexOf('if (!settled) {'), SRC.indexOf('=settle_declined'))
    expect(declined).toMatch(/'SETTLE_BLOCKED'/)
  })
})
