/**
 * Tests for the US equity market calendar (full-closure holidays + early closes).
 *
 * Root cause of the 2026-05-26 incident: isMarketOpen()/isInEntryWindow() only
 * checked weekday + time, with no holiday calendar. SPARK therefore traded on
 * Memorial Day (Mon 2026-05-25), spawning untracked positions. These tests pin
 * the calendar so a closed market is never treated as open.
 */
import { describe, it, expect } from 'vitest'
import { isMarketHoliday, isEarlyClose, marketCloseMinuteCT } from '../market-calendar'

/** Build a Date whose local fields represent the given CT wall-clock — matches
 *  how the scanner passes `ct` (a getCTNow() Date read via getDay()/getHours()). */
function ct(y: number, m: number, d: number, hh = 12, mm = 0): Date {
  return new Date(y, m - 1, d, hh, mm, 0)
}

describe('market-calendar', () => {
  describe('isMarketHoliday (full closures)', () => {
    it('flags Memorial Day 2026 (Mon May 25) — the incident date', () => {
      expect(isMarketHoliday(ct(2026, 5, 25))).toBe(true)
    })

    it('does NOT flag a normal trading day (Tue May 26 2026)', () => {
      expect(isMarketHoliday(ct(2026, 5, 26))).toBe(false)
    })

    it("flags New Year's Day 2026 (Thu Jan 1)", () => {
      expect(isMarketHoliday(ct(2026, 1, 1))).toBe(true)
    })

    it('flags Christmas 2025 (Thu Dec 25)', () => {
      expect(isMarketHoliday(ct(2025, 12, 25))).toBe(true)
    })

    it('flags observed Independence Day 2026 (Fri Jul 3, since Jul 4 is Sat)', () => {
      expect(isMarketHoliday(ct(2026, 7, 3))).toBe(true)
    })

    it('flags Good Friday 2026 (Apr 3)', () => {
      expect(isMarketHoliday(ct(2026, 4, 3))).toBe(true)
    })

    it('flags Thanksgiving 2025 (Thu Nov 27)', () => {
      expect(isMarketHoliday(ct(2025, 11, 27))).toBe(true)
    })
  })

  describe('early closes (1:00 PM ET = 12:00 PM CT)', () => {
    it('marks the day after Thanksgiving 2025 (Fri Nov 28) as an early close', () => {
      expect(isEarlyClose(ct(2025, 11, 28))).toBe(true)
      expect(marketCloseMinuteCT(ct(2025, 11, 28))).toBe(1200)
    })

    it('marks Christmas Eve 2025 (Wed Dec 24) as an early close', () => {
      expect(isEarlyClose(ct(2025, 12, 24))).toBe(true)
    })

    it('a normal day closes at 3:00 PM CT (1500) and is not an early close', () => {
      expect(isEarlyClose(ct(2026, 5, 26))).toBe(false)
      expect(marketCloseMinuteCT(ct(2026, 5, 26))).toBe(1500)
    })

    it('a full holiday is not reported as merely an early close', () => {
      expect(isEarlyClose(ct(2026, 5, 25))).toBe(false)
    })
  })
})
