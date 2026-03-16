/**
 * Tests for pt-tiers.ts — market hours, PT tier logic, and formatCloseReason.
 */

import { describe, it, expect } from 'vitest'
import {
  getCTMinutes,
  isMarketOpen,
  getCurrentPTTier,
  secondsUntilNextTier,
  formatCloseReason,
} from '../pt-tiers'

/* ================================================================== */
/*  getCTMinutes                                                       */
/* ================================================================== */

describe('getCTMinutes', () => {
  it('returns 0 for midnight', () => {
    const d = new Date('2026-03-16T00:00:00')
    expect(getCTMinutes(d)).toBe(0)
  })

  it('returns 510 for 8:30 AM', () => {
    const d = new Date('2026-03-16T08:30:00')
    expect(getCTMinutes(d)).toBe(510)
  })

  it('returns 900 for 3:00 PM', () => {
    const d = new Date('2026-03-16T15:00:00')
    expect(getCTMinutes(d)).toBe(900)
  })
})

/* ================================================================== */
/*  isMarketOpen                                                       */
/* ================================================================== */

describe('isMarketOpen', () => {
  it('returns true at 9:30 AM weekday', () => {
    // Monday March 16 2026
    const d = new Date('2026-03-16T09:30:00')
    expect(isMarketOpen(d)).toBe(true)
  })

  it('returns true at 2:59 PM weekday', () => {
    const d = new Date('2026-03-16T14:59:00')
    expect(isMarketOpen(d)).toBe(true)
  })

  it('returns false at 3:00 PM (market closed)', () => {
    const d = new Date('2026-03-16T15:00:00')
    expect(isMarketOpen(d)).toBe(false)
  })

  it('returns false before 8:30 AM', () => {
    const d = new Date('2026-03-16T08:29:00')
    expect(isMarketOpen(d)).toBe(false)
  })

  it('returns false on Saturday', () => {
    // March 21 2026 is Saturday
    const d = new Date('2026-03-21T10:00:00')
    expect(isMarketOpen(d)).toBe(false)
  })

  it('returns false on Sunday', () => {
    const d = new Date('2026-03-22T10:00:00')
    expect(isMarketOpen(d)).toBe(false)
  })
})

/* ================================================================== */
/*  getCurrentPTTier                                                   */
/* ================================================================== */

describe('getCurrentPTTier', () => {
  it('returns MORNING (30%) before 10:30 AM', () => {
    const d = new Date('2026-03-16T09:00:00')
    const tier = getCurrentPTTier(d)
    expect(tier.pct).toBe(0.30)
    expect(tier.label).toBe('Morning')
  })

  it('returns MIDDAY (20%) between 10:30 AM and 12:59 PM', () => {
    const d = new Date('2026-03-16T11:00:00')
    const tier = getCurrentPTTier(d)
    expect(tier.pct).toBe(0.20)
    expect(tier.label).toBe('Midday')
  })

  it('returns AFTERNOON (15%) at 1:00 PM', () => {
    const d = new Date('2026-03-16T13:00:00')
    const tier = getCurrentPTTier(d)
    expect(tier.pct).toBe(0.15)
    expect(tier.label).toBe('Afternoon')
  })

  it('returns AFTERNOON at 2:44 PM', () => {
    const d = new Date('2026-03-16T14:44:00')
    const tier = getCurrentPTTier(d)
    expect(tier.pct).toBe(0.15)
  })

  it('tier transition at exactly 10:30 AM', () => {
    const d = new Date('2026-03-16T10:30:00')
    const tier = getCurrentPTTier(d)
    expect(tier.pct).toBe(0.20) // switched to MIDDAY
  })

  it('tier transition at exactly 1:00 PM', () => {
    const d = new Date('2026-03-16T13:00:00')
    const tier = getCurrentPTTier(d)
    expect(tier.pct).toBe(0.15) // switched to AFTERNOON
  })
})

/* ================================================================== */
/*  secondsUntilNextTier                                               */
/* ================================================================== */

describe('secondsUntilNextTier', () => {
  it('returns seconds until MIDDAY when in MORNING', () => {
    const d = new Date('2026-03-16T10:00:00')
    const result = secondsUntilNextTier(d)
    expect(result).not.toBeNull()
    expect(result!.nextLabel).toBe('20% Midday')
    // 10:00 → 10:30 = 30 minutes = 1800 seconds
    expect(result!.seconds).toBe(1800)
  })

  it('returns seconds until AFTERNOON when in MIDDAY', () => {
    const d = new Date('2026-03-16T12:00:00')
    const result = secondsUntilNextTier(d)
    expect(result).not.toBeNull()
    expect(result!.nextLabel).toBe('15% Afternoon')
    // 12:00 → 13:00 = 60 minutes = 3600 seconds
    expect(result!.seconds).toBe(3600)
  })

  it('returns seconds until EOD when in AFTERNOON', () => {
    const d = new Date('2026-03-16T14:00:00')
    const result = secondsUntilNextTier(d)
    expect(result).not.toBeNull()
    expect(result!.nextLabel).toBe('EOD cutoff')
    // 14:00 → 14:45 = 45 minutes = 2700 seconds
    expect(result!.seconds).toBe(2700)
  })

  it('returns null after 2:45 PM', () => {
    const d = new Date('2026-03-16T14:50:00')
    const result = secondsUntilNextTier(d)
    expect(result).toBeNull()
  })
})

/* ================================================================== */
/*  formatCloseReason                                                  */
/* ================================================================== */

describe('formatCloseReason', () => {
  it('formats morning profit target', () => {
    const result = formatCloseReason('profit_target_morning')
    expect(result.text).toContain('Morning')
    expect(result.text).toContain('30%')
    expect(result.color).toContain('emerald')
  })

  it('formats midday profit target', () => {
    const result = formatCloseReason('profit_target_midday')
    expect(result.text).toContain('Midday')
    expect(result.text).toContain('20%')
  })

  it('formats afternoon profit target', () => {
    const result = formatCloseReason('profit_target_afternoon')
    expect(result.text).toContain('Afternoon')
    expect(result.text).toContain('15%')
  })

  it('formats stop loss', () => {
    const result = formatCloseReason('stop_loss')
    expect(result.text).toBe('Stop Loss')
    expect(result.color).toContain('red')
  })

  it('formats EOD cutoff', () => {
    const result = formatCloseReason('eod_cutoff')
    expect(result.text).toBe('EOD Cutoff')
  })

  it('formats eod_safety', () => {
    const result = formatCloseReason('eod_safety')
    expect(result.text).toBe('EOD Cutoff')
  })

  it('formats stale holdover', () => {
    const result = formatCloseReason('stale_holdover')
    expect(result.text).toBe('Stale Holdover')
  })

  it('formats data feed failure', () => {
    const result = formatCloseReason('data_feed_failure')
    expect(result.text).toBe('Data Failure')
    expect(result.color).toContain('red')
  })

  it('formats unknown reasons by replacing underscores', () => {
    const result = formatCloseReason('some_custom_reason')
    expect(result.text).toBe('some custom reason')
  })
})
