import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'

/**
 * THE GUARD FIRED, THE CLOSER DEFERRED, THE POSITION WAS ASSIGNED.
 *
 * 2026-08-28, SPARK-SPY-20260828-K9JKRK (0DTE, expiry that day, short put 773):
 * `closeAtRiskBeforeBell` detected the risk correctly and called `closePosition`,
 * which returned 'deferred' — twice. SPY settled 769.39, so the position went into
 * settlement $3.61 ITM and was assigned. Sandbox, one lot, no real money — but
 * `isProductionBot('spark')` is true, so that is the identical path a live account
 * runs, and the assignment guard shipped 2026-08-27 exists precisely to stop this.
 *
 * Three defects, three invariants pinned here:
 *
 *  1. 'deferred' means "the order is live, next cycle will re-poll". At 14:57 CT on a
 *     0DTE there IS no next cycle — the window shuts and the contract expires. On the
 *     guard path a resting order must read as 'failed', never as a soft pending status.
 *
 *  2. The guard re-selects on `status = 'open'`, and a deferred close leaves the row
 *     open. Without a pending-order check, every cycle in the window fires ANOTHER
 *     closing order. Harmless on one sandbox lot; on a live multi-lot position
 *     duplicate closing orders can sell through it and open a short.
 *
 *  3. Every failure wrote CRITICAL to `{bot}_logs` — and stopped there. Nobody was
 *     told. A CRITICAL row in a table is not an alert.
 *
 * These are source-level assertions because the functions are module-private, which is
 * the same approach close-outcome.test.ts takes to the sibling invariant.
 */

const SRC = readFileSync(join(__dirname, '..', 'scanner.ts'), 'utf8')

/** The body of closeAtRiskBeforeBell, from its signature to the next top-level fn. */
function guardBody(): string {
  const start = SRC.indexOf('async function closeAtRiskBeforeBell(')
  expect(start, 'closeAtRiskBeforeBell must exist').toBeGreaterThan(-1)
  const rest = SRC.slice(start + 1)
  const end = rest.search(/\n(?:async )?function \w+\(/)
  return end === -1 ? rest : rest.slice(0, end)
}

/** The body of closePosition, from its signature to the next top-level fn. */
function closePositionBody(): string {
  const start = SRC.indexOf('async function closePosition(')
  expect(start, 'closePosition must exist').toBeGreaterThan(-1)
  const rest = SRC.slice(start + 1)
  const end = rest.search(/\n(?:async )?function \w+\(/)
  return end === -1 ? rest : rest.slice(0, end)
}

describe('a resting order is not a close when there is no next cycle', () => {
  it('closePosition accepts a mustCloseNow flag', () => {
    expect(closePositionBody()).toMatch(/mustCloseNow\?: boolean/)
  })

  it('the assignment guard sets mustCloseNow when it calls closePosition', () => {
    const body = guardBody()
    const call = body.slice(body.indexOf('const outcome = await closePosition('))
    expect(call.slice(0, 400)).toMatch(/true,\s*\/\/ mustCloseNow/)
  })

  it('the defer branch returns failed — not deferred — under mustCloseNow', () => {
    const body = closePositionBody()
    const guardIdx = body.indexOf('if (mustCloseNow) {')
    const deferIdx = body.indexOf("return 'deferred'")
    expect(guardIdx, 'a mustCloseNow branch must exist').toBeGreaterThan(-1)
    expect(deferIdx, "the 'deferred' return must still exist").toBeGreaterThan(-1)
    // The escape hatch must come BEFORE the deferred return, or it never runs.
    expect(guardIdx).toBeLessThan(deferIdx)
    expect(body.slice(guardIdx, deferIdx)).toMatch(/return 'failed'/)
  })

  it("still returns 'deferred' on the ordinary path — a healthy limit close is not broken", () => {
    // The 2026-08-26 sweep exists because relabelling every deferral as a failure
    // flags FLAME's normal debit-limit profit-target exit as broken. Keep both states.
    expect(closePositionBody()).toMatch(/return 'deferred'/)
  })
})

describe('never stack a second close order on a live one', () => {
  it('the guard reads the pending close order off the position row', () => {
    const body = guardBody()
    expect(body).toMatch(/sandbox_close_order_id/)
  })

  it('a position with a live close order is skipped, not re-closed', () => {
    const body = guardBody()
    const pendingIdx = body.indexOf('if (pendingClose) {')
    const closeIdx = body.indexOf('const outcome = await closePosition(')
    expect(pendingIdx, 'a pending-order check must exist').toBeGreaterThan(-1)
    // The check must precede the close call, and must bail out of the iteration.
    expect(pendingIdx).toBeLessThan(closeIdx)
    expect(body.slice(pendingIdx, closeIdx)).toMatch(/continue/)
  })
})

describe('a CRITICAL row in a logs table is not an alert', () => {
  it('the guard escalates off-box when a position ends the window exposed', () => {
    const body = guardBody()
    // ntfy is what reaches a phone; Discord carries the readable record. Both, as the
    // expired-position watchdog already does.
    expect(body).toMatch(/sendOpsPush\(/)
    expect(body).toMatch(/postOpsAlert\(/)
    expect(body).toMatch(/severity: 'critical'/)
  })

  it('every unguarded outcome feeds the alert, not just a failed close', () => {
    const body = guardBody()
    // Three ways to end the window still exposed. All three must reach `exposed`,
    // or the alert quietly under-reports the risk it exists to surface.
    const pushes = body.match(/exposed\.push\(/g) ?? []
    expect(pushes.length).toBeGreaterThanOrEqual(3)
    // no_quote is the easiest one to forget: unguarded IS exposed.
    const noQuote = body.slice(body.indexOf("reason: 'no_quote'"))
    expect(noQuote.slice(0, 400)).toMatch(/exposed\.push\(/)
  })

  it('an alert failure can never take the scan cycle down', () => {
    const body = guardBody()
    const alertIdx = body.indexOf('sendOpsPush(')
    expect(body.slice(alertIdx)).toMatch(/\.catch\(/)
    // void-prefixed so the guard does not await a notification channel
    expect(body).toMatch(/void sendOpsPush\(/)
    expect(body).toMatch(/void postOpsAlert\(/)
  })
})
