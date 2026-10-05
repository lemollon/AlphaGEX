import { describe, it, expect } from 'vitest'
import { todaySeries, periodSeries } from './account-series'

describe('todaySeries', () => {
  it('drops points with no equity and maps timestamp to ms', () => {
    const out = todaySeries([
      { timestamp: '2026-10-05T14:30:00.000Z', equity: 10_500 },
      { timestamp: '2026-10-05T14:31:00.000Z', equity: null as unknown as number },
      { timestamp: '2026-10-05T14:32:00.000Z', equity: 10_520 },
    ])
    expect(out).toEqual([
      { t: new Date('2026-10-05T14:30:00.000Z').getTime(), v: 10_500 },
      { t: new Date('2026-10-05T14:32:00.000Z').getTime(), v: 10_520 },
    ])
  })

  it('returns empty for undefined input, never throws', () => {
    expect(todaySeries(undefined)).toEqual([])
  })
})

describe('periodSeries', () => {
  const intraday = [{ timestamp: '2026-10-05T14:30:00.000Z', equity: 10_000 }]
  const curve = [
    { t: '2026-09-01T00:00:00.000Z', equity: 9_000 },
    { t: '2026-09-20T00:00:00.000Z', equity: 9_400 },
    { t: '2026-10-01T00:00:00.000Z', equity: 9_900 },
    { t: '2026-10-05T00:00:00.000Z', equity: 10_200 },
  ]

  it('today reads the intraday series, not the equity curve', () => {
    expect(periodSeries('today', intraday, curve)).toEqual([
      { t: new Date('2026-10-05T14:30:00.000Z').getTime(), v: 10_000 },
    ])
  })

  it('week keeps only points within ~9 calendar days of the curve end', () => {
    const out = periodSeries('week', intraday, curve)
    expect(out.map((p) => p.v)).toEqual([9_900, 10_200])
  })

  it('month keeps a wider trailing window than week', () => {
    const out = periodSeries('month', intraday, curve)
    expect(out.map((p) => p.v)).toEqual([9_400, 9_900, 10_200])
  })

  it('life returns the full curve untouched', () => {
    const out = periodSeries('life', intraday, curve)
    expect(out.map((p) => p.v)).toEqual([9_000, 9_400, 9_900, 10_200])
  })

  it('handles a missing equity curve without throwing', () => {
    expect(periodSeries('life', intraday, undefined)).toEqual([])
  })
})
