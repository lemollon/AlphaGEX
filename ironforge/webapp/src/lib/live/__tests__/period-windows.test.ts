import { describe, it, expect } from 'vitest'
import { weekStartET, monthStartET } from '../period-windows'

/**
 * The bug this replaces: home.ts used `now() - interval '7 days'` / `'30
 * days'` — a rolling window, not the calendar week/month the Forge stats
 * card's "This Week" / "This Month" labels promise. These lock the actual
 * reset boundaries: Monday 00:00:00 ET for the week, the 1st 00:00:00 ET for
 * the month, in Eastern (the exchange's clock), not Central or UTC.
 */
describe('weekStartET', () => {
  it('a trade closed Sunday 23:59 ET belongs to the PRIOR week', () => {
    // Week of Mon 2026-08-31 (EDT, UTC-4).
    const sunday2359ET = new Date('2026-08-30T23:59:00-04:00')
    const mondayMorningET = new Date('2026-08-31T10:00:00-04:00')
    const boundary = weekStartET(mondayMorningET)
    expect(sunday2359ET.getTime()).toBeLessThan(boundary.getTime())
  })

  it('a trade closed Monday 00:01 ET belongs to the NEW week', () => {
    const monday0001ET = new Date('2026-08-31T00:01:00-04:00')
    const boundary = weekStartET(monday0001ET)
    expect(monday0001ET.getTime()).toBeGreaterThanOrEqual(boundary.getTime())
  })

  it('resolves to Monday 00:00:00 ET as a UTC instant', () => {
    const mondayMorningET = new Date('2026-08-31T10:00:00-04:00')
    expect(weekStartET(mondayMorningET).toISOString()).toBe('2026-08-31T04:00:00.000Z')
  })

  it('holds across a DST fall-back transition (Nov 1, 2026)', () => {
    // EST (UTC-5) is already in effect the Monday after the transition.
    const mondayAfterFallBack = new Date('2026-11-02T12:00:00-05:00')
    expect(weekStartET(mondayAfterFallBack).toISOString()).toBe('2026-11-02T05:00:00.000Z')
  })
})

describe('monthStartET', () => {
  it('a trade closed the last day of the month at 23:59 ET belongs to the PRIOR month', () => {
    const aug31_2359ET = new Date('2026-08-31T23:59:00-04:00')
    const sep1_0001ET = new Date('2026-09-01T00:01:00-04:00')
    const boundary = monthStartET(sep1_0001ET)
    expect(aug31_2359ET.getTime()).toBeLessThan(boundary.getTime())
  })

  it('a trade closed the 1st at 00:01 ET belongs to the NEW month', () => {
    const sep1_0001ET = new Date('2026-09-01T00:01:00-04:00')
    const boundary = monthStartET(sep1_0001ET)
    expect(sep1_0001ET.getTime()).toBeGreaterThanOrEqual(boundary.getTime())
  })

  it('resolves to the 1st, 00:00:00 ET, as a UTC instant', () => {
    const midMonthET = new Date('2026-09-15T10:00:00-04:00')
    expect(monthStartET(midMonthET).toISOString()).toBe('2026-09-01T04:00:00.000Z')
  })
})
