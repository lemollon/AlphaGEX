import { describe, it, expect } from 'vitest'
import {
  deriveLifecycleNodes,
  lifecycleFillFraction,
  formatLocalClock,
  minutesSince,
  formatElapsedMinutes,
  formatTargetStopCaption,
  formatAutoCloseCaption,
} from '@/live/lifecycle'

describe('deriveLifecycleNodes', () => {
  it('open: Opened is done, Monitoring is current, the rest are future', () => {
    const nodes = deriveLifecycleNodes(false)
    expect(nodes.map((n) => n.status)).toEqual(['done', 'current', 'future', 'future'])
  })

  it('closed: every node is done', () => {
    const nodes = deriveLifecycleNodes(true)
    expect(nodes.map((n) => n.status)).toEqual(['done', 'done', 'done', 'done'])
  })
})

describe('lifecycleFillFraction', () => {
  it('fills to Monitoring (1/3) for an open position', () => {
    expect(lifecycleFillFraction(deriveLifecycleNodes(false))).toBeCloseTo(1 / 3, 5)
  })

  it('fills the whole track once closed', () => {
    expect(lifecycleFillFraction(deriveLifecycleNodes(true))).toBe(1)
  })

  it('is 0 when nothing has been reached', () => {
    expect(
      lifecycleFillFraction([
        { label: 'Opened', status: 'future' },
        { label: 'Monitoring', status: 'future' },
        { label: 'Target / Stop', status: 'future' },
        { label: 'Auto Close', status: 'future' },
      ]),
    ).toBe(0)
  })
})

describe('formatLocalClock', () => {
  it('formats an ISO timestamp as h:mm AM/PM in the device local time', () => {
    // 18:05 UTC on a date with no DST ambiguity — assert shape, not a fixed
    // zone, since the whole point is "local", not Central.
    expect(formatLocalClock('2026-01-15T18:05:00.000Z')).toMatch(/^\d{1,2}:\d{2} (AM|PM)$/)
  })

  it('is null for missing or invalid input — never a fabricated time', () => {
    expect(formatLocalClock(null)).toBeNull()
    expect(formatLocalClock(undefined)).toBeNull()
    expect(formatLocalClock('not-a-date')).toBeNull()
  })
})

describe('minutesSince', () => {
  it('computes whole-ish minutes elapsed from an ISO timestamp', () => {
    const opened = new Date('2026-01-15T18:00:00.000Z').toISOString()
    const now = new Date('2026-01-15T18:37:00.000Z').getTime()
    expect(minutesSince(opened, now)).toBeCloseTo(37, 5)
  })

  it('never goes negative on clock skew', () => {
    const opened = new Date('2026-01-15T18:10:00.000Z').toISOString()
    const now = new Date('2026-01-15T18:00:00.000Z').getTime()
    expect(minutesSince(opened, now)).toBe(0)
  })

  it('is 0 for an invalid timestamp', () => {
    expect(minutesSince('not-a-date')).toBe(0)
  })
})

describe('formatElapsedMinutes', () => {
  it('shows "N min" under an hour', () => {
    expect(formatElapsedMinutes(0)).toBe('0 min')
    expect(formatElapsedMinutes(37)).toBe('37 min')
    expect(formatElapsedMinutes(59.4)).toBe('59 min')
  })

  it('rounds up into the next hour bucket right at the boundary', () => {
    expect(formatElapsedMinutes(59.6)).toBe('1 h 0 min')
  })

  it('shows "H h M min" at or beyond an hour', () => {
    expect(formatElapsedMinutes(60)).toBe('1 h 0 min')
    expect(formatElapsedMinutes(72)).toBe('1 h 12 min')
    expect(formatElapsedMinutes(125)).toBe('2 h 5 min')
  })

  it('clamps negative input to zero', () => {
    expect(formatElapsedMinutes(-5)).toBe('0 min')
  })
})

describe('formatTargetStopCaption', () => {
  it('formats "$target / −$stop" when both are known', () => {
    expect(formatTargetStopCaption(60, 120)).toBe('$60 / −$120')
  })

  it('reads "hold to close" when the strategy has no real stop', () => {
    expect(formatTargetStopCaption(60, null)).toBe('hold to close')
    expect(formatTargetStopCaption(null, null)).not.toBe('hold to close')
  })

  it('is a dash when neither figure is known', () => {
    expect(formatTargetStopCaption(null, null)).toBe('—')
  })

  it('rounds and uses the real minus sign for the stop figure', () => {
    expect(formatTargetStopCaption(59.6, 119.6)).toBe('$60 / −$120')
  })
})

describe('formatAutoCloseCaption', () => {
  it('reads "by <local time>" when a scheduled close instant is known', () => {
    expect(formatAutoCloseCaption('2026-01-15T20:00:00.000Z')).toMatch(/^by \d{1,2}:\d{2} (AM|PM)$/)
  })

  it('falls back to "at close" when no same-day instant is known', () => {
    expect(formatAutoCloseCaption(null)).toBe('at close')
    expect(formatAutoCloseCaption(undefined)).toBe('at close')
  })
})
