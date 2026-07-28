import { describe, it, expect } from 'vitest'
import { isAfterTrialCloseTime, marketDateKey, TRIAL_CLOSE_MINUTES_CT } from '../trial-close'
import { isEligibleTradingDay } from '../trading-days'

/** Build a local Date standing in for a CT wall-clock reading, as getCTNow() returns. */
const ctAt = (y: number, m: number, d: number, hh: number, mm: number) => new Date(y, m - 1, d, hh, mm)

describe('isAfterTrialCloseTime — the guard that stops a day being counted early', () => {
  it('refuses every minute of the session', () => {
    // 15:00 CT is the equity close; the ledger waits a further 5 min for settlement.
    for (const [hh, mm] of [[0, 0], [8, 29], [8, 30], [12, 0], [14, 50], [14, 59], [15, 0], [15, 4]]) {
      expect(isAfterTrialCloseTime(ctAt(2026, 7, 28, hh, mm))).toBe(false)
    }
  })

  it('allows from 15:05 CT to end of day', () => {
    for (const [hh, mm] of [[15, 5], [15, 6], [16, 0], [23, 59]]) {
      expect(isAfterTrialCloseTime(ctAt(2026, 7, 28, hh, mm))).toBe(true)
    }
  })

  it('sits after the bots own EOD cutoff (14:50 CT), not before it', () => {
    // If this inverted, a day could be counted while positions were still being closed.
    expect(TRIAL_CLOSE_MINUTES_CT).toBeGreaterThan(14 * 60 + 50)
  })
})

describe('the time gate and the date gate are independent', () => {
  // This pairing is the actual bug risk: isEligibleTradingDay answers "is this DATE a
  // trading day", NOT "is the session over". Neither guard covers the other's job.
  it('a weekday morning is an eligible DATE but must not be counted yet', () => {
    const ct = ctAt(2026, 7, 28, 9, 0) // Tuesday 9am CT
    expect(isEligibleTradingDay({ ct }).eligible).toBe(true)
    expect(isAfterTrialCloseTime(ct)).toBe(false)
  })

  it('a weekend evening passes the time gate but is not an eligible date', () => {
    const ct = ctAt(2026, 7, 26, 18, 0) // Sunday 6pm CT
    expect(isAfterTrialCloseTime(ct)).toBe(true)
    expect(isEligibleTradingDay({ ct }).eligible).toBe(false)
  })

  it('only a weekday after the close satisfies both', () => {
    const ct = ctAt(2026, 7, 28, 15, 30)
    expect(isAfterTrialCloseTime(ct)).toBe(true)
    expect(isEligibleTradingDay({ ct }).eligible).toBe(true)
  })
})

describe('marketDateKey', () => {
  it('formats a zero-padded local calendar date', () => {
    expect(marketDateKey(ctAt(2026, 7, 28, 15, 30))).toBe('2026-07-28')
    expect(marketDateKey(ctAt(2026, 1, 5, 0, 1))).toBe('2026-01-05')
  })

  it('does not roll to the next day for a late-evening CT time', () => {
    // A UTC-based formatter would print the 29th here. That would count one calendar
    // day twice and skip another.
    expect(marketDateKey(ctAt(2026, 7, 28, 23, 30))).toBe('2026-07-28')
  })

  it('is stable across the in-process dedupe (same date → same key)', () => {
    expect(marketDateKey(ctAt(2026, 7, 28, 15, 5))).toBe(marketDateKey(ctAt(2026, 7, 28, 22, 45)))
  })
})
