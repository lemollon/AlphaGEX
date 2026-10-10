import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'
import { closeStatusPrefix, stillOpen, type CloseOutcome } from '../settle-watchdog'

/**
 * NEVER ANNOUNCE A CLOSE YOU HAVE NOT READ BACK — EVERYWHERE, NOT JUST THE SETTLE PATH.
 *
 * PR #2911 fixed `settleExpiredPositions`, which logged `SETTLED ... pnl=$35.00` once a
 * minute for three days about positions that stayed `status = 'open'`. A sweep for the
 * same shape found it in **ten more places**: `closePosition` returned a result and
 * 10 of its 12 callers threw it away, then returned `closed:<reason>`.
 *
 * That string is not cosmetic. It drives
 * `action = status.startsWith('closed:') ? 'closed' : 'monitoring'` and is written into
 * `{bot}_logs` as the SCAN reason — so the bot's own log could say
 * `closed: profit_target` or `closed: stop_loss` for a close that never landed.
 *
 * 🚨 A BOOLEAN COULD NOT FIX THIS. `false` meant two different things: a genuine
 * failure, and a legitimate DEFERRAL — a debit-limit close order placed and awaiting
 * its fill, which is the NORMAL path for FLAME's profit-target exit. A mechanical
 * `if (!ok) report failure` sweep would have relabelled every healthy FLAME limit close
 * as broken. Hence three states, and three honest reports.
 */

const SRC = readFileSync(join(__dirname, '..', 'scanner.ts'), 'utf8')

describe('the three outcomes map to three honest statuses', () => {
  it('only a real close may carry the closed: prefix', () => {
    // `closed:` is what flips `action` to 'closed' downstream. Nothing else may.
    expect(closeStatusPrefix('closed')).toBe('closed:')
    expect(closeStatusPrefix('deferred')).toBe('pending_close:')
    expect(closeStatusPrefix('failed')).toBe('close_failed:')
  })

  it('neither a deferral nor a failure starts with closed:', () => {
    for (const o of ['deferred', 'failed'] as CloseOutcome[]) {
      expect(closeStatusPrefix(o).startsWith('closed:')).toBe(false)
    }
  })

  it('a deferral and a failure both leave the position open', () => {
    expect(stillOpen('closed')).toBe(false)
    expect(stillOpen('deferred')).toBe(true)
    expect(stillOpen('failed')).toBe(true)
  })

  it('reproduces the downstream action rule for each outcome', () => {
    const action = (o: CloseOutcome) =>
      `${closeStatusPrefix(o)}stop_loss@1.2300`.startsWith('closed:') ? 'closed' : 'monitoring'
    expect(action('closed')).toBe('closed')
    expect(action('deferred')).toBe('monitoring')
    expect(action('failed')).toBe('monitoring')
  })
})

describe('EVERY closePosition caller now reports the real outcome', () => {
  const CALLERS = SRC.split('\n')
    .map((line, i) => ({ line, n: i + 1 }))
    .filter(({ line }) => /\bawait closePosition\(/.test(line))

  it('finds every call site (guards against this test silently covering nothing)', () => {
    expect(CALLERS.length).toBeGreaterThanOrEqual(12)
  })

  it('🚨 no caller discards the result', () => {
    // `await closePosition(` with nothing on the left-hand side IS the bug: the caller
    // cannot possibly report the truth if it never looked at the answer.
    const discarding = CALLERS.filter(({ line }) => /^\s*await closePosition\(/.test(line))
    expect(discarding.map(c => c.n)).toEqual([])
  })

  it('no exit path announces closed: unconditionally any more', () => {
    // The literal shape that was wrong in seven places.
    expect(SRC).not.toMatch(/return \{ status: `closed:\$\{reason\}`/)
    expect(SRC).not.toMatch(/return \{ status: `closed:stop_loss@/)
    expect(SRC).not.toMatch(/return \{ status: `closed:profit_target@/)
    expect(SRC).not.toMatch(/return \{ status: `closed:trailing_lockin@/)
    expect(SRC).not.toMatch(/return \{ status: `closed:eod_cutoff@/)
    expect(SRC).not.toMatch(/return \{ status: `closed:data_feed_failure\(/)
  })

  it('routes each exit reason through reportClose', () => {
    for (const frag of [
      "reportClose(bot, pid, slOutcome, 'stop_loss'",
      'reportClose(bot, pid, ptOutcome, `profit_target_${ptTier}`',
      "reportClose(bot, pid, tlOutcome, 'trailing_lockin'",
      "reportClose(bot, pid, sgOutcome, 'eod_cutoff'",
      "reportClose(bot, pid, dfOutcome, 'data_feed_failure'",
      'reportClose(bot, pid, fcOutcome, reason, reason)',
    ]) {
      expect(SRC).toContain(frag)
    }
  })

  it('reportClose warns only on a real failure, never on a pending fill', () => {
    const fn = SRC.slice(SRC.indexOf('function reportClose('), SRC.indexOf('async function closePosition('))
    expect(fn).toMatch(/if \(outcome === 'failed'\) \{/)
    expect(fn).toMatch(/CLOSE DID NOT COMPLETE/)
    expect(fn).toMatch(/closeStatusPrefix\(outcome\)/)
    // A deferral is healthy — it must not produce a warning line.
    expect(fn).not.toMatch(/deferred['"]\s*\)\s*\{[\s\S]{0,80}console\.warn/)
  })
})

describe('the two paths that were already right stay right', () => {
  it('the settle path treats only closed as settled', () => {
    expect(SRC).toMatch(/const settled = settleOutcome === 'closed'/)
  })

  it('the EOD safety net stops claiming a catch it did not make', () => {
    expect(SRC).toMatch(/const netOutcome = await closePosition\(/)
    expect(SRC).toMatch(/if \(netOutcome === 'closed'\) \{/)
    expect(SRC).toMatch(/EOD SAFETY NET DID NOT CLOSE/)
  })

  it('the deferred-fill return no longer sits outside its own rowsAffected guard', () => {
    // It used to report `closed:deferred_fill` even when the UPDATE matched 0 rows.
    expect(SRC).toMatch(/close_failed:deferred_fill@/)
    expect(SRC).toMatch(/fill arrived[\s\S]{0,80}but the UPDATE matched 0 rows/)
  })
})
