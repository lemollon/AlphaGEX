import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { join } from 'path'
import {
  HEARTBEAT_CHECK_HHMM,
  HEARTBEAT_SILENT_DAYS,
  evaluateTradeHeartbeat,
  isStrategySkip,
  type HeartbeatDay,
} from '../trade-heartbeat'

/**
 * "THIS BOT HAS NOT TRADED" — the symptom net.
 *
 * The expired-position watchdog fixes ONE cause. This catches the symptom whatever the
 * cause: FLAME and SPARK each expect roughly one entry per trading day, so a run of
 * trading days with zero opens and no STRATEGY reason for it means something is broken.
 * It would have fired on 8/22 — four days before a human noticed the page looked stuck.
 *
 * The allowlist is the whole design, and it must fail toward NOISE, not toward silence:
 * a plumbing skip (`skip:no_paper_account`, `skip:insufficient_bp`) is exactly the class
 * of silent failure this exists to catch, so it must never read as an explanation.
 */

const SRC = readFileSync(join(__dirname, '..', 'scanner.ts'), 'utf8')

const day = (date: string, opens: number, reasons: string[] = []): HeartbeatDay =>
  ({ date, opens, reasons })

describe('a quiet day is explained only by a skip the STRATEGY chose', () => {
  it('accepts the real strategy skips, with their live parameter formats', () => {
    expect(isStrategySkip('skip:vix_elevated(1.410>1.25)')).toBe(true)
    expect(isStrategySkip('skip:vix_too_high(41.0>cap40)')).toBe(true)
    expect(isStrategySkip('skip:already_traded_today')).toBe(true)
    expect(isStrategySkip('max_trades_reached(1/1)')).toBe(true)
    expect(isStrategySkip('skip:standdown_after_loss')).toBe(true)
    expect(isStrategySkip('skip:credit_too_low($0.0800 at sd=2.1)')).toBe(true)
    expect(isStrategySkip('skip:event_blackout(CPI until 8:45 AM CT)')).toBe(true)
  })

  it('🚨 REJECTS plumbing skips — those ARE the failures this net exists to catch', () => {
    expect(isStrategySkip('skip:no_paper_account')).toBe(false)
    expect(isStrategySkip('skip:insufficient_bp($120 < $200/contract)')).toBe(false)
    expect(isStrategySkip('skip:low_bp($90)')).toBe(false)
    expect(isStrategySkip('skip:tradier_not_configured')).toBe(false)
    expect(isStrategySkip('skip:no_paper_balance($0)')).toBe(false)
    expect(isStrategySkip('skip:production_order_failed(401)')).toBe(false)
    expect(isStrategySkip('vix_unavailable(timeout)')).toBe(false)
    expect(isStrategySkip('vix_unknown(have=3 need=20)')).toBe(false)
  })

  it('rejects the reason SPARK actually logged while it was stuck', () => {
    // Three days of `monitoring | monitoring` — an unsettled position blocking entry
    // never reaches the entry gate at all, so there is no skip reason to find.
    expect(isStrategySkip('monitoring')).toBe(false)
    expect(isStrategySkip('')).toBe(false)
  })

  it('defaults an unrecognised reason to UNEXPLAINED', () => {
    // Over-alerting on a new strategy skip is recoverable. Going blind on a new
    // failure mode is what cost three trading days.
    expect(isStrategySkip('skip:some_gate_invented_next_quarter')).toBe(false)
  })
})

describe('the run is CONSECUTIVE, counted back from the newest trading day', () => {
  it('fires after N unexplained zero-open trading days', () => {
    const v = evaluateTradeHeartbeat('spark', [
      day('2026-08-20', 1),
      day('2026-08-21', 0, ['monitoring']),
      day('2026-08-24', 0, ['monitoring']),
    ])
    expect(v.silent).toBe(true)
    expect(v.silentDays).toBe(2)
    expect(v.dates).toEqual(['2026-08-21', '2026-08-24'])
    expect(v.message).toMatch(/SPARK has not opened a position in 2 trading days/)
  })

  it('stays quiet on a single quiet day — one day is noise', () => {
    const v = evaluateTradeHeartbeat('spark', [day('2026-08-24', 1), day('2026-08-25', 0, ['monitoring'])])
    expect(v.silent).toBe(false)
    expect(v.silentDays).toBe(1)
    expect(v.message).toBeNull()
  })

  it('breaks the run on a day that actually traded', () => {
    const v = evaluateTradeHeartbeat('spark', [
      day('2026-08-19', 0, ['monitoring']),
      day('2026-08-20', 0, ['monitoring']),
      day('2026-08-21', 1),
      day('2026-08-24', 0, ['monitoring']),
    ])
    expect(v.silentDays).toBe(1)
    expect(v.silent).toBe(false)
  })

  it('breaks the run on a day the strategy explained', () => {
    const v = evaluateTradeHeartbeat('spark', [
      day('2026-08-21', 0, ['monitoring']),
      day('2026-08-24', 0, ['skip:vix_elevated(1.41>1.25)']),
      day('2026-08-25', 0, ['monitoring']),
    ])
    expect(v.silentDays).toBe(1)
    expect(v.silent).toBe(false)
  })

  it('one strategy reason anywhere in the day explains that day', () => {
    // Every scan cycle logs a reason; the entry gate fires once. The day is explained
    // if ANY of its reasons is a strategy skip, not only the last one.
    const v = evaluateTradeHeartbeat('spark', [
      day('2026-08-24', 0, ['monitoring', 'skip:already_traded_today', 'outside_entry_window']),
      day('2026-08-25', 0, ['monitoring']),
    ])
    expect(v.silentDays).toBe(1)
  })

  it('a day with NO scan logs at all counts as silence — a dead scanner is a failure', () => {
    const v = evaluateTradeHeartbeat('spark', [day('2026-08-24', 0, []), day('2026-08-25', 0, [])])
    expect(v.silent).toBe(true)
  })

  it('says nothing when there is no history to judge', () => {
    expect(evaluateTradeHeartbeat('spark', []).silent).toBe(false)
  })

  it('would have fired on the incident itself', () => {
    // SPARK's 8/21 position stranded; 8/24 and 8/25 both went by with entries blocked
    // and only `monitoring | monitoring` in the log.
    const v = evaluateTradeHeartbeat('spark', [
      day('2026-08-21', 1, ['monitoring']),
      day('2026-08-24', 0, ['monitoring']),
      day('2026-08-25', 0, ['monitoring']),
    ])
    expect(v.silent).toBe(true)
    expect(v.message).toMatch(/2026-08-24\.\.2026-08-25/)
  })
})

describe('the check is wired into the scan cycle', () => {
  it('runs once per CT trading day, after every entry window has closed', () => {
    expect(HEARTBEAT_SILENT_DAYS).toBe(2)
    expect(HEARTBEAT_CHECK_HHMM).toBe(1430)
    expect(SRC).toMatch(/if \(_lastHeartbeatDate\[bot\.name\] === todayStr\) return/)
    expect(SRC).toMatch(/if \(ctHHMM\(ct\) < HEARTBEAT_CHECK_HHMM\) return/)
  })

  it('claims the day BEFORE the work, so a thrown query cannot make it fire every minute', () => {
    const fn = SRC.slice(
      SRC.indexOf('async function tradeHeartbeatCheck('),
      SRC.indexOf('const verdict = evaluateTradeHeartbeat('),
    )
    expect(fn.length).toBeGreaterThan(500)
    expect(fn.indexOf('_lastHeartbeatDate[bot.name] = todayStr')).toBeLessThan(fn.indexOf('await query('))
  })

  it('never invents history for a bot whose tables are only days old', () => {
    expect(SRC).toMatch(/if \(knownDates\.length === 0\) return/)
    expect(SRC).toMatch(/if \(iso < firstKnown\) continue/)
  })

  it('counts trading days only — weekends and full-closure holidays are skipped', () => {
    expect(SRC).toMatch(/if \(dow === 0 \|\| dow === 6\) continue/)
    expect(SRC).toMatch(/if \(isMarketHoliday\(probe\)\) continue/)
  })

  it('is called from scanBot and can never take the cycle down', () => {
    expect(SRC).toMatch(/try \{\s*await tradeHeartbeatCheck\(bot, ct\)\s*\} catch/)
  })

  it('escalates to a phone-capable alert, not only to a console line', () => {
    const fn = SRC.slice(SRC.indexOf('async function tradeHeartbeatCheck('))
    expect(fn).toMatch(/HAS NOT TRADED/)
    expect(fn).toMatch(/postOpsAlert\(\{[\s\S]{0,400}?severity: 'critical'/)
  })
})

describe('a critical ops alert admits when it cannot reach a phone', () => {
  it('mentions the user id when one is configured, because @here does NOT push', () => {
    const disc = readFileSync(join(__dirname, '..', 'discord.ts'), 'utf8')
    expect(disc).toMatch(/DISCORD_ALERT_USER_ID/)
    expect(disc).toMatch(/return `<@\$\{id\}> `/)
    // ...and says so out loud rather than pretending someone was reached.
    expect(disc).toMatch(/no phone push/)
  })
})
