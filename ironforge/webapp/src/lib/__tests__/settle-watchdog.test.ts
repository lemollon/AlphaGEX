import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'
import {
  WatchdogLedger,
  WATCHDOG_CYCLES_BEFORE_ACT,
  WATCHDOG_MAX_ATTEMPTS,
  WATCHDOG_SETTLE_REASON,
  decideWatchdog,
  isBookOnlyCloseReason,
  isPastExpiry,
  normalizeExpiration,
  settlementPnl,
  settlementValue,
  summarizeWatchdogRun,
  type SpreadLegs,
} from '../settle-watchdog'

/**
 * THE WATCHDOG MUST FIX THE BOOK, AND IT MUST NEVER LIE ABOUT A PRICE.
 *
 * SPARK's 8/21, 8/24 and 8/25 positions sat `status = 'open'` for three trading days
 * while the log printed `SETTLED ... pnl=$35.00` once a minute. The CAUSE was fixed in
 * PR #2911. This file pins the fix for the DETECTION failure: a backstop pass that
 * settles the stranded position itself and reports what it did, because an alarm only
 * converts a silent failure into a notification somebody still has to act on.
 *
 * Two guards are the whole design, and both have already been violated for real money
 * in this codebase:
 *   1. NEVER INVENT A PRICE — `max(0.0, val)` once booked MAX PROFIT on ITM credit
 *      expiries, and a $0 force-close mark did the same thing a second time.
 *   2. CIRCUIT BREAKER — the bug being replaced WAS an infinite retry loop.
 *
 * Most of this file is behavioural, against the real exported functions. The
 * source-text pins at the end cover the wiring a unit test cannot reach.
 */

const SRC = readFileSync(join(__dirname, '..', 'scanner.ts'), 'utf8')

/** SPARK's real structure: a put credit spread, $2 wing, 1 contract. */
const PUT_SPREAD: SpreadLegs = { putShort: 762, putLong: 760, callShort: 0, callLong: 0 }

/** An iron condor, so the value math is not silently put-only. */
const CONDOR: SpreadLegs = { putShort: 500, putLong: 495, callShort: 520, callLong: 525 }

function input(over: Partial<Parameters<typeof decideWatchdog>[0]> = {}) {
  return {
    cyclesSeen: WATCHDOG_CYCLES_BEFORE_ACT,
    attempts: 0,
    tripped: false,
    settleClose: 770,
    legs: PUT_SPREAD,
    ...over,
  }
}

describe('GUARD 1 — the watchdog never invents a settlement price', () => {
  it('refuses to settle when there is no daily bar for the expiration date', () => {
    const d = decideWatchdog(input({ settleClose: null }))
    expect(d.action).toBe('escalate')
    expect(d).toMatchObject({ cause: 'no_settle_price' })
  })

  it('treats a $0 close as NO price, never as a $0 settlement', () => {
    // The whole failure mode: a 0 that reads as "worthless" books MAX PROFIT.
    expect(settlementValue(PUT_SPREAD, 0)).toBeNull()
    expect(decideWatchdog(input({ settleClose: 0 })).action).toBe('escalate')
  })

  it('refuses a NaN or negative close rather than clamping it to something plausible', () => {
    expect(settlementValue(PUT_SPREAD, NaN)).toBeNull()
    expect(settlementValue(PUT_SPREAD, -5)).toBeNull()
  })

  it('books MAX LOSS, not max profit, when the spread expired fully through the short', () => {
    // SPY closed at 755 with a 760/762 put spread: both legs ITM, worth the full wing.
    expect(settlementValue(PUT_SPREAD, 755)).toBe(2)
    expect(settlementPnl(0.35, 2, 1)).toBe(-165)
  })

  it('books intrinsic — not 0, not the wing — when the close lands between the strikes', () => {
    expect(settlementValue(PUT_SPREAD, 761.25)).toBe(0.75)
  })

  it('books max profit only when the close is genuinely above the short strike', () => {
    expect(settlementValue(PUT_SPREAD, 770)).toBe(0)
    expect(settlementPnl(0.35, 0, 1)).toBe(35)
  })

  it('settles the call side of a condor too, so an ITM call wing is not booked as a win', () => {
    expect(settlementValue(CONDOR, 530)).toBe(5)   // call wing fully breached
    expect(settlementValue(CONDOR, 522)).toBe(2)   // call short breached by 2
    expect(settlementValue(CONDOR, 510)).toBe(0)   // expired inside both wings
    expect(settlementValue(CONDOR, 490)).toBe(5)   // put wing fully breached
  })

  it('refuses a malformed row instead of guessing what the wings were', () => {
    expect(settlementValue({ putShort: 762, putLong: 762, callShort: 0, callLong: 0 }, 770)).toBeNull()
    expect(settlementValue({ putShort: 0, putLong: 0, callShort: 0, callLong: 0 }, 770)).toBeNull()
  })
})

describe('GUARD 2 — the circuit breaker, because the bug it replaces was a retry loop', () => {
  it('escalates instead of force-settling a position it has already force-settled', () => {
    const d = decideWatchdog(input({ attempts: WATCHDOG_MAX_ATTEMPTS }))
    expect(d.action).toBe('escalate')
    expect(d).toMatchObject({ cause: 'circuit_breaker' })
  })

  it('allows exactly one attempt, ever', () => {
    expect(WATCHDOG_MAX_ATTEMPTS).toBe(1)
    expect(decideWatchdog(input({ attempts: 0 })).action).toBe('settle')
    expect(decideWatchdog(input({ attempts: 1 })).action).toBe('escalate')
  })

  it('checks the breaker BEFORE the price guard, so a broken fixer cannot be masked', () => {
    const d = decideWatchdog(input({ attempts: 1, settleClose: null }))
    expect(d).toMatchObject({ cause: 'circuit_breaker' })
  })

  it('goes quiet after escalating — an alert every 60s is an alert nobody reads', () => {
    expect(decideWatchdog(input({ tripped: true })).action).toBe('silent')
    expect(decideWatchdog(input({ tripped: true, attempts: 5 })).action).toBe('silent')
  })
})

describe('the normal settle path gets its turn first', () => {
  it('waits out the first sighting instead of racing the pass it backstops', () => {
    expect(WATCHDOG_CYCLES_BEFORE_ACT).toBe(2)
    expect(decideWatchdog(input({ cyclesSeen: 1 })).action).toBe('wait')
    expect(decideWatchdog(input({ cyclesSeen: 2 })).action).toBe('settle')
  })

  it('acts on the second consecutive sighting with the value it computed', () => {
    const d = decideWatchdog(input({ cyclesSeen: 2, settleClose: 761 }))
    expect(d).toMatchObject({ action: 'settle', value: 1, settleClose: 761 })
  })
})

describe('the ledger counts CONSECUTIVE cycles, not total sightings', () => {
  it('counts up while a position keeps offending', () => {
    const l = new WatchdogLedger()
    l.observe(['A'])
    expect(l.cyclesSeen('A')).toBe(1)
    l.observe(['A'])
    expect(l.cyclesSeen('A')).toBe(2)
  })

  it('forgets a position the moment it stops offending', () => {
    // A settled position must not carry a stale count into a future incident —
    // otherwise the next stranded row is force-settled on its FIRST sighting.
    const l = new WatchdogLedger()
    l.observe(['A'])
    l.observe([])
    expect(l.cyclesSeen('A')).toBe(0)
    l.observe(['A'])
    expect(l.cyclesSeen('A')).toBe(1)
  })

  it('tracks attempts and the tripped flag per position, not globally', () => {
    const l = new WatchdogLedger()
    l.observe(['A', 'B'])
    l.recordAttempt('A')
    l.trip('A')
    expect(l.attemptsFor('A')).toBe(1)
    expect(l.isTripped('A')).toBe(true)
    expect(l.attemptsFor('B')).toBe(0)
    expect(l.isTripped('B')).toBe(false)
  })
})

describe('only STRICTLY past expiry is the watchdog\'s business', () => {
  it('leaves expiry day alone — the position is live until the close', () => {
    expect(isPastExpiry('2026-08-26', '2026-08-26')).toBe(false)
  })

  it('leaves a swing hold expiring later alone', () => {
    expect(isPastExpiry('2026-08-28', '2026-08-26')).toBe(false)
  })

  it('claims the three positions that actually stuck', () => {
    for (const exp of ['2026-08-21', '2026-08-24', '2026-08-25']) {
      expect(isPastExpiry(exp, '2026-08-26')).toBe(true)
    }
  })

  it('reads a pg DATE as a Date, not as its locale rendering', () => {
    // String(new Date('2026-08-24')) is "Mon Aug 24 ..." — sliced to 10 chars it is
    // "Mon Aug 24", which never equals a daily bar's `date`. That exact conversion is
    // why the settle path matched nothing for its first ten days alive.
    expect(normalizeExpiration(new Date('2026-08-24T00:00:00Z'))).toBe('2026-08-24')
    expect(isPastExpiry(new Date('2026-08-24T00:00:00Z'), '2026-08-26')).toBe(true)
  })
})

describe('the report is an FYI when it healed and loud when it could not', () => {
  it('says nothing when nothing happened', () => {
    expect(summarizeWatchdogRun('spark', [], [])).toBeNull()
  })

  it('reads as the target message: what it fixed, how much, and that entries are free', () => {
    const s = summarizeWatchdogRun('spark', [
      { positionId: 'SPARK-SPY-20260821-R4K55H', value: 0, pnl: 34 },
      { positionId: 'SPARK-SPY-20260824-SGPTDQ', value: 0, pnl: 35 },
      { positionId: 'SPARK-SPY-20260825-JZF35P', value: 0, pnl: 23 },
    ], [])
    expect(s?.severity).toBe('info')
    expect(s?.text).toBe(
      'SPARK: force-settled 3 expired positions, +$92.00, entries unblocked.',
    )
  })

  it('escalates loudly when it tried and could not, and says entries are still blocked', () => {
    const s = summarizeWatchdogRun('spark', [], [
      { positionId: 'SPARK-SPY-20260821-R4K55H', cause: 'no_settle_price', detail: 'no daily bar' },
    ])
    expect(s?.severity).toBe('critical')
    expect(s?.text).toMatch(/could NOT settle 1 expired position/)
    expect(s?.text).toMatch(/BLOCKED/)
  })

  it('is critical whenever anything failed, even if other positions healed', () => {
    const s = summarizeWatchdogRun('spark', [{ positionId: 'A', value: 0, pnl: 10 }], [
      { positionId: 'B', cause: 'circuit_breaker', detail: 'looped' },
    ])
    expect(s?.severity).toBe('critical')
    expect(s?.text).toMatch(/1 other position did settle/)
  })
})

describe('a watchdog settle never reaches the broker', () => {
  it('names the watchdog reason as book-only alongside the normal settle', () => {
    expect(isBookOnlyCloseReason(WATCHDOG_SETTLE_REASON)).toBe(true)
    expect(isBookOnlyCloseReason('settled_at_expiry')).toBe(true)
    expect(isBookOnlyCloseReason('profit_target_MORNING')).toBe(false)
    expect(isBookOnlyCloseReason('stop_loss')).toBe(false)
  })

  it('closePosition derives its expired-contract test from that predicate', () => {
    // Not a literal string compare in scanner.ts — one definition, shared, so adding a
    // book-only reason can never leave a close path mirroring to a dead contract.
    expect(SRC).toMatch(/const isExpiredContract =\s*\n\s*isBookOnlyCloseReason\(reason\) \|\|/)
  })
})

describe('the watchdog is wired into the scan cycle as a backstop, not a UI poll', () => {
  it('runs in scanBot immediately after the normal settle pass', () => {
    const cycle = SRC.slice(SRC.indexOf('async function scanBot('))
    const settleAt = cycle.indexOf('await settleExpiredPositions(bot, ct)')
    const watchdogAt = cycle.indexOf('await watchdogForceSettleExpired(bot, ct)')
    expect(settleAt).toBeGreaterThan(-1)
    expect(watchdogAt).toBeGreaterThan(settleAt)
  })

  it('can never take the scan cycle down', () => {
    expect(SRC).toMatch(
      /try \{\s*const repaired = await watchdogForceSettleExpired\(bot, ct\)[\s\S]{0,200}?\} catch/,
    )
  })

  it('selects STRICTLY past-expiry open rows for this bot', () => {
    expect(SRC).toMatch(/WHERE status = 'open' AND dte_mode = \$1 AND expiration < \$2::date/)
  })

  it('observes the full offender set every cycle, including the empty one', () => {
    // `observe` must run BEFORE the early return, or a healed position keeps its count.
    const fn = SRC.slice(
      SRC.indexOf('async function watchdogForceSettleExpired('),
      SRC.indexOf('/** Per-bot guard so the heartbeat runs'),
    )
    expect(fn.length).toBeGreaterThan(1000)
    expect(fn.indexOf('ledger.observe(offenders)')).toBeLessThan(fn.indexOf('if (rows.length === 0) return'))
  })

  it('reads the durable attempt count out of the log table, not just process memory', () => {
    // A redeploy resets a Map. It must not re-arm the loop.
    expect(SRC).toMatch(/attempts = Math\.max\(attempts, int\(priorRows\[0\]\?\.n\)\)/)
    // ...and a failed read must assume the breaker is ARMED, never that it is clear.
    expect(SRC).toMatch(/attempts = Math\.max\(attempts, WATCHDOG_MAX_ATTEMPTS\)/)
  })

  it('records the attempt BEFORE making it, so a crash mid-repair still counts', () => {
    const fn = SRC.slice(
      SRC.indexOf('// ---- decision.action === \'settle\''),
      SRC.indexOf('repaired.push('),
    )
    expect(fn.indexOf('ledger.recordAttempt(positionId)')).toBeLessThan(fn.indexOf('await closePosition('))
    expect(fn.indexOf('WATCHDOG_ATTEMPT_PREFIX')).toBeLessThan(fn.indexOf('await closePosition('))
  })

  it('trips the breaker when the force-settle does not move the row', () => {
    expect(SRC).toMatch(/if \(!closed\) \{[\s\S]{0,400}?ledger\.trip\(positionId\)/)
    expect(SRC).toMatch(/WATCHDOG FORCE-SETTLE DID NOT CLOSE/)
  })

  it('only claims a repair after closePosition reports the row actually moved', () => {
    // The original bug in one line: a confident log parallel to the write, not
    // downstream of it. `repaired` must be fed by the boolean, never by the attempt.
    const fn = SRC.slice(
      SRC.indexOf('async function watchdogForceSettleExpired('),
      SRC.indexOf('/** Per-bot guard so the heartbeat runs'),
    )
    expect(fn.indexOf('if (!closed) {')).toBeLessThan(fn.indexOf('repaired.push('))
  })
})
