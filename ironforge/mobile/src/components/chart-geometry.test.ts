import { describe, it, expect } from 'vitest'
import { chartGeometry, nearestIndex, type Point } from '@/components/chart-geometry'

const W = 300
const H = 88
const PAD = 10

function series(...pnls: number[]): Point[] {
  return pnls.map((pnl, i) => ({ timestamp: `2026-08-20T14:${String(i).padStart(2, '0')}:00Z`, pnl }))
}

describe('chartGeometry — the y-domain always contains zero', () => {
  it('includes zero when the whole trade is under water', () => {
    // The dangerous case: -40 recovering to -10. Scaled to its own min/max this is a
    // confident upward line with no breakeven in frame — it reads as a winner.
    const g = chartGeometry(series(-40, -25, -10), W, H, PAD)!
    expect(g.domain.lo).toBe(-40)
    expect(g.domain.hi).toBe(0)
    // Breakeven is inside the plot area, so the dashed line is actually visible.
    expect(g.zeroY).toBeGreaterThanOrEqual(0)
    expect(g.zeroY).toBeLessThanOrEqual(H)
  })

  it('includes zero when the whole trade is in profit', () => {
    const g = chartGeometry(series(10, 60, 126), W, H, PAD)!
    expect(g.domain.lo).toBe(0)
    expect(g.domain.hi).toBe(126)
    expect(g.zeroY).toBeLessThanOrEqual(H)
  })

  it('puts a losing value BELOW the breakeven line on screen', () => {
    // y grows downward in SVG, so "below breakeven" means a larger y than zeroY.
    const g = chartGeometry(series(-40, -25, -10), W, H, PAD)!
    expect(g.y(-25)).toBeGreaterThan(g.zeroY)
    expect(g.y(0)).toBeCloseTo(g.zeroY, 6)
  })

  it('puts a winning value ABOVE the breakeven line on screen', () => {
    const g = chartGeometry(series(10, 60, 126), W, H, PAD)!
    expect(g.y(60)).toBeLessThan(g.zeroY)
  })

  it('survives a flat series sitting exactly on breakeven', () => {
    const g = chartGeometry(series(0, 0, 0), W, H, PAD)!
    expect(Number.isFinite(g.zeroY)).toBe(true)
    expect(g.points).not.toMatch(/NaN/)
  })

  it('never emits NaN for a single sample', () => {
    const g = chartGeometry(series(42), W, H, PAD)!
    expect(g.points).not.toMatch(/NaN/)
    expect(g.x(0)).toBe(W / 2)
  })

  it('keeps every plotted point inside the padded plot area', () => {
    const g = chartGeometry(series(-40, 0, 126, -12), W, H, PAD)!
    for (const v of [-40, 0, 126, -12]) {
      expect(g.y(v)).toBeGreaterThanOrEqual(PAD - 1e-9)
      expect(g.y(v)).toBeLessThanOrEqual(H - PAD + 1e-9)
    }
  })

  it('returns null rather than dividing by zero on an unmeasured layout', () => {
    expect(chartGeometry(series(1, 2), 0, H, PAD)).toBeNull()
    expect(chartGeometry([], W, H, PAD)).toBeNull()
  })
})

describe('nearestIndex — snaps to a real sample', () => {
  it('maps the ends to the first and last samples', () => {
    expect(nearestIndex(0, W, 5)).toBe(0)
    expect(nearestIndex(W, W, 5)).toBe(4)
  })

  it('never returns an index outside the series', () => {
    for (const x of [-500, -1, 0, 1, W / 2, W, W + 500]) {
      const i = nearestIndex(x, W, 5)
      expect(i).toBeGreaterThanOrEqual(0)
      expect(i).toBeLessThanOrEqual(4)
    }
  })

  it('degenerates safely with fewer than two samples', () => {
    expect(nearestIndex(123, W, 1)).toBe(0)
    expect(nearestIndex(123, 0, 5)).toBe(0)
  })
})
