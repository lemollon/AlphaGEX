/**
 * Tests for traffic.ts — the pure aggregation/shaping helpers behind
 * GET /api/ops/traffic. No database: the route runs two grouped SQL queries
 * and hands the raw rows to these functions, so this is where the day-range
 * math and the zero-fill/sort logic actually get exercised.
 */

import { describe, it, expect } from 'vitest'
import { ctDayRange, shapePages, shapeWaitlistByDay, type PageViewRow, type WaitlistDayRow } from '../traffic'

/* ================================================================== */
/*  ctDayRange                                                        */
/* ================================================================== */

describe('ctDayRange', () => {
  it('returns `count` days, ascending, ending on the CT date of `now`', () => {
    const days = ctDayRange(5, new Date('2026-09-03T18:00:00Z')) // 1:00 PM CT
    expect(days).toEqual(['2026-08-30', '2026-08-31', '2026-09-01', '2026-09-02', '2026-09-03'])
  })

  it('a single day is just today', () => {
    expect(ctDayRange(1, new Date('2026-09-03T18:00:00Z'))).toEqual(['2026-09-03'])
  })

  it('clamps count below 1 up to 1', () => {
    expect(ctDayRange(0, new Date('2026-09-03T18:00:00Z'))).toEqual(['2026-09-03'])
    expect(ctDayRange(-5, new Date('2026-09-03T18:00:00Z'))).toEqual(['2026-09-03'])
  })

  it('is correct across a UTC-date boundary (late evening CT is still the same CT day)', () => {
    // 2026-09-04 03:00 UTC = 2026-09-03 ~10 PM CDT — still Sept 3 in Chicago.
    const days = ctDayRange(3, new Date('2026-09-04T03:00:00Z'))
    expect(days).toEqual(['2026-09-01', '2026-09-02', '2026-09-03'])
  })

  it('every entry is a distinct calendar date with no gaps', () => {
    const days = ctDayRange(30, new Date('2026-09-03T18:00:00Z'))
    expect(days).toHaveLength(30)
    expect(new Set(days).size).toBe(30)
    for (let i = 1; i < days.length; i++) {
      const prev = new Date(`${days[i - 1]}T12:00:00Z`)
      const cur = new Date(`${days[i]}T12:00:00Z`)
      expect(cur.getTime() - prev.getTime()).toBe(86_400_000)
    }
  })
})

/* ================================================================== */
/*  shapePages                                                        */
/* ================================================================== */

describe('shapePages', () => {
  const days = ['2026-09-01', '2026-09-02', '2026-09-03']

  it('groups rows by path and sums totals', () => {
    const rows: PageViewRow[] = [
      { day: '2026-09-01', path: '/live', visitors: 10, views: 15 },
      { day: '2026-09-02', path: '/live', visitors: 5, views: 6 },
      { day: '2026-09-01', path: '/waitlist', visitors: 2, views: 2 },
    ]
    const pages = shapePages(rows, days)
    const live = pages.find((p) => p.path === '/live')!
    expect(live.totalVisitors).toBe(15)
    expect(live.totalViews).toBe(21)
  })

  it('zero-fills every day in range, even with no rows for that day', () => {
    const rows: PageViewRow[] = [{ day: '2026-09-01', path: '/live', visitors: 10, views: 15 }]
    const pages = shapePages(rows, days)
    const live = pages.find((p) => p.path === '/live')!
    expect(live.byDay).toEqual({
      '2026-09-01': { visitors: 10, views: 15 },
      '2026-09-02': { visitors: 0, views: 0 },
      '2026-09-03': { visitors: 0, views: 0 },
    })
  })

  it('sorts pages by totalVisitors descending', () => {
    const rows: PageViewRow[] = [
      { day: '2026-09-01', path: '/small', visitors: 1, views: 1 },
      { day: '2026-09-01', path: '/big', visitors: 100, views: 100 },
      { day: '2026-09-01', path: '/medium', visitors: 10, views: 10 },
    ]
    const pages = shapePages(rows, days)
    expect(pages.map((p) => p.path)).toEqual(['/big', '/medium', '/small'])
  })

  it('returns an empty array for no rows', () => {
    expect(shapePages([], days)).toEqual([])
  })
})

/* ================================================================== */
/*  shapeWaitlistByDay                                                */
/* ================================================================== */

describe('shapeWaitlistByDay', () => {
  const days = ['2026-09-01', '2026-09-02', '2026-09-03']

  it('zero-fills every day, overlaying known counts', () => {
    const rows: WaitlistDayRow[] = [{ day: '2026-09-02', c: 7 }]
    expect(shapeWaitlistByDay(rows, days)).toEqual({
      '2026-09-01': 0,
      '2026-09-02': 7,
      '2026-09-03': 0,
    })
  })

  it('all zero when there are no rows', () => {
    expect(shapeWaitlistByDay([], days)).toEqual({
      '2026-09-01': 0,
      '2026-09-02': 0,
      '2026-09-03': 0,
    })
  })
})
