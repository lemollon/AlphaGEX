import { describe, it, expect } from 'vitest'
import { accountChartGeometry, nearestAccountIndex } from './account-chart-geometry'
import type { AccountPoint } from '@/live/account-series'

const W = 300
const H = 150
const PAD = 12

function series(...vs: number[]): AccountPoint[] {
  return vs.map((v, i) => ({ t: i * 60_000, v }))
}

describe('accountChartGeometry — plots a level, not a P&L delta', () => {
  it('does NOT force zero into the domain for a far-from-zero balance', () => {
    const g = accountChartGeometry(series(10_000, 10_200, 10_150), W, H, PAD)!
    expect(g.domain.lo).toBeGreaterThan(0)
    expect(g.domain.hi).toBeLessThan(11_000)
  })

  it('keeps every plotted value inside the padded plot area', () => {
    const g = accountChartGeometry(series(9_800, 10_000, 10_400, 9_950), W, H, PAD)!
    for (const v of [9_800, 10_000, 10_400, 9_950]) {
      expect(g.y(v)).toBeGreaterThanOrEqual(PAD - 1e-9)
      expect(g.y(v)).toBeLessThanOrEqual(H - PAD + 1e-9)
    }
  })

  it('a rising series draws a line that goes up on screen (smaller y)', () => {
    const g = accountChartGeometry(series(10_000, 10_500), W, H, PAD)!
    expect(g.y(10_500)).toBeLessThan(g.y(10_000))
  })

  it('survives a flat series without NaN', () => {
    const g = accountChartGeometry(series(10_000, 10_000, 10_000), W, H, PAD)!
    expect(g.points).not.toMatch(/NaN/)
  })

  it('returns null for fewer than two points or an unmeasured layout', () => {
    expect(accountChartGeometry(series(10_000), W, H, PAD)).toBeNull()
    expect(accountChartGeometry([], W, H, PAD)).toBeNull()
    expect(accountChartGeometry(series(1, 2), 0, H, PAD)).toBeNull()
  })
})

describe('nearestAccountIndex', () => {
  it('maps the ends to the first and last samples', () => {
    expect(nearestAccountIndex(0, W, 5)).toBe(0)
    expect(nearestAccountIndex(W, W, 5)).toBe(4)
  })

  it('never returns an index outside the series', () => {
    for (const x of [-500, -1, 0, 1, W / 2, W, W + 500]) {
      const i = nearestAccountIndex(x, W, 5)
      expect(i).toBeGreaterThanOrEqual(0)
      expect(i).toBeLessThanOrEqual(4)
    }
  })

  it('degenerates safely with fewer than two samples', () => {
    expect(nearestAccountIndex(123, W, 1)).toBe(0)
    expect(nearestAccountIndex(123, 0, 5)).toBe(0)
  })
})
