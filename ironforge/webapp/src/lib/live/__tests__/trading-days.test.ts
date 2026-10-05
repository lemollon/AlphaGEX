import { describe, it, expect } from 'vitest'
import { lastNTradingDays, sumTradingDayWindow, dailyResultBars, agentLead, cumulativePnlSeries } from '../trading-days'

/**
 * dev-handoff §6 KPI contract: "Past week" = last 5 TRADING days including
 * today, "Past month" = last 21 TRADING days including today — not a
 * Monday-reset calendar week or a 1st-of-month calendar reset. Gap audit
 * flagged the shipped /api/live/performance as PARTIAL for using a rolling
 * 7/30 CALENDAR-day window instead.
 */
describe('lastNTradingDays', () => {
  it('skips weekends — Monday 2026-10-05 looking back 5 days reaches into the prior week', () => {
    // 2026-10-05 is a Monday.
    const monday = new Date(2026, 9, 5)
    const days = lastNTradingDays(5, monday)
    expect(days).toEqual(['2026-09-29', '2026-09-30', '2026-10-01', '2026-10-02', '2026-10-05'])
  })

  it('skips a full-closure holiday (Labor Day, 2026-09-07)', () => {
    const tuesdayAfterLaborDay = new Date(2026, 8, 8) // 2026-09-08
    const days = lastNTradingDays(3, tuesdayAfterLaborDay)
    // 09-07 (Mon) is Labor Day — skipped. Prior trading day is 09-04 (Fri).
    expect(days).toEqual(['2026-09-03', '2026-09-04', '2026-09-08'])
  })

  it('returns exactly n days', () => {
    expect(lastNTradingDays(21, new Date(2026, 9, 5))).toHaveLength(21)
  })
})

describe('sumTradingDayWindow', () => {
  it('excludes a point just outside the trading-day window', () => {
    const monday = new Date(2026, 9, 5)
    const points = [
      { day: '2026-09-28', pnl: 1000 }, // outside the last-5 window (starts 09-29)
      { day: '2026-09-29', pnl: 100 },
      { day: '2026-10-05', pnl: 50 },
    ]
    expect(sumTradingDayWindow(points, 5, monday)).toBe(150)
  })
})

describe('dailyResultBars', () => {
  it('zero-fills days with no closed trade', () => {
    const monday = new Date(2026, 9, 5)
    const bars = dailyResultBars([{ day: '2026-10-05', pnl: 42 }], 5, monday)
    expect(bars).toHaveLength(5)
    expect(bars[bars.length - 1]).toEqual({ day: '2026-10-05', pnl: 42 })
    expect(bars[0].pnl).toBe(0)
  })
})

describe('agentLead', () => {
  it('counts winning trading days over total trading days', () => {
    const points = [
      { day: '2026-10-01', pnl: 50 },
      { day: '2026-10-02', pnl: -20 },
      { day: '2026-10-02', pnl: 30 }, // same day, second trade — still one trading day, net positive
      { day: '2026-10-05', pnl: -10 },
    ]
    expect(agentLead(points)).toEqual({ kept: 2, total: 3 })
  })

  it('returns null with no closed trades', () => {
    expect(agentLead([])).toBeNull()
  })
})

describe('cumulativePnlSeries', () => {
  it('is cumulative-from-zero, not an equity curve', () => {
    const points = [
      { t: 1, day: '2026-10-01', pnl: 100 },
      { t: 2, day: '2026-10-02', pnl: -40 },
    ]
    const series = cumulativePnlSeries(points, null)
    expect(series.map((p) => p.pnl)).toEqual([100, 60])
  })

  it('restarts at zero per window — a 1W slice does not carry prior weeks’ total', () => {
    const monday = new Date(2026, 9, 5)
    const points = [
      { t: new Date(2026, 8, 20).getTime(), day: '2026-09-21', pnl: 5000 }, // well before the window
      { t: new Date(2026, 9, 5).getTime(), day: '2026-10-05', pnl: 10 },
    ]
    const series = cumulativePnlSeries(points, 5, monday)
    expect(series).toEqual([{ t: new Date(2026, 9, 5).toISOString(), pnl: 10 }])
  })
})
