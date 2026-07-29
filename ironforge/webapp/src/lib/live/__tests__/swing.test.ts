import { describe, it, expect } from 'vitest'
import { deriveSwingMeta, isSwingActive } from '../swing'

/**
 * These two values drive a badge telling a customer whether their money sat in the
 * market overnight, and a "Day N" counter beside it. Off-by-one here is the kind of
 * thing nobody notices until someone asks why a trade opened this morning claims to
 * have been held overnight.
 */

describe('deriveSwingMeta', () => {
  it('a trade opened today is Day 1 and NOT held overnight', () => {
    expect(deriveSwingMeta('2026-07-29', '2026-07-29')).toEqual({
      heldOvernight: false,
      dayNumber: 1,
    })
  })

  it('yesterday is Day 2 and held overnight', () => {
    expect(deriveSwingMeta('2026-07-28', '2026-07-29')).toEqual({
      heldOvernight: true,
      dayNumber: 2,
    })
  })

  it('counts calendar days across a weekend', () => {
    // Friday open, seen Monday: three calendar days later.
    expect(deriveSwingMeta('2026-07-24', '2026-07-27')).toEqual({
      heldOvernight: true,
      dayNumber: 4,
    })
  })

  it('crosses a month boundary correctly', () => {
    expect(deriveSwingMeta('2026-07-31', '2026-08-01')).toEqual({
      heldOvernight: true,
      dayNumber: 2,
    })
  })

  it('crosses a year boundary correctly', () => {
    expect(deriveSwingMeta('2026-12-31', '2027-01-01')).toEqual({
      heldOvernight: true,
      dayNumber: 2,
    })
  })

  it('is not fooled by a DST transition', () => {
    // US DST ends 2026-11-01. Parsing both as UTC midnight means the 25-hour local day
    // cannot round to 0 or 2 — the reason this compares date STRINGS, not timestamps.
    expect(deriveSwingMeta('2026-10-31', '2026-11-01')).toEqual({
      heldOvernight: true,
      dayNumber: 2,
    })
    expect(deriveSwingMeta('2026-11-01', '2026-11-02')).toEqual({
      heldOvernight: true,
      dayNumber: 2,
    })
  })

  it('treats a missing open date as a fresh position, never as an overnight claim', () => {
    // Asserting "held overnight" without an open time would state something unsupported.
    expect(deriveSwingMeta(null, '2026-07-29')).toEqual({ heldOvernight: false, dayNumber: 1 })
  })

  it('falls back safely on an unparseable date', () => {
    expect(deriveSwingMeta('not-a-date', '2026-07-29')).toEqual({ heldOvernight: false, dayNumber: 1 })
  })

  it('clamps a future open date to Day 1 rather than Day 0 or negative', () => {
    expect(deriveSwingMeta('2026-07-30', '2026-07-29')).toEqual({
      heldOvernight: false,
      dayNumber: 1,
    })
  })
})

describe('isSwingActive — when the extra card belongs on screen', () => {
  const today = { held_overnight: false }
  const swung = { held_overnight: true }

  it('is false for no positions', () => {
    expect(isSwingActive([])).toBe(false)
    expect(isSwingActive(null)).toBe(false)
    expect(isSwingActive(undefined)).toBe(false)
  })

  it('is false for a single position, swung or not', () => {
    // One position has nothing to compare against; the two-card view exists to show
    // yesterday's leg BESIDE today's.
    expect(isSwingActive([today])).toBe(false)
    expect(isSwingActive([swung])).toBe(false)
  })

  it('is FALSE for two positions opened the same day', () => {
    // The bug this exists for: paper currently holds two positions both opened
    // 2026-07-29. Triggering on count alone rendered a swing layout showing two
    // "Opened Today" cards — a swing that never happened.
    expect(isSwingActive([today, today])).toBe(false)
  })

  it('is true when one of two positions was carried overnight', () => {
    expect(isSwingActive([swung, today])).toBe(true)
    expect(isSwingActive([today, swung])).toBe(true)
  })

  it('is true when both legs were carried overnight', () => {
    expect(isSwingActive([swung, swung])).toBe(true)
  })
})
