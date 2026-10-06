import { describe, it, expect } from 'vitest'
import {
  chartGeometry,
  timeChartGeometry,
  nearestIndex,
  nearestTimeIndex,
  tooltipX,
  formatPnl,
  formatAxisDollar,
  formatAxisTime,
  type Point,
} from '@/components/chart-geometry'

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

describe('tooltipX — the box never clips outside the chart', () => {
  const BOX = 88
  const INSET = 4

  it('centers the box under a point in the middle of the chart', () => {
    expect(tooltipX(W / 2, BOX, W, INSET)).toBe(W / 2 - BOX / 2)
  })

  it('slides the box inward instead of clipping off the left edge', () => {
    expect(tooltipX(0, BOX, W, INSET)).toBe(INSET)
    expect(tooltipX(-50, BOX, W, INSET)).toBe(INSET)
  })

  it('slides the box inward instead of clipping off the right edge', () => {
    expect(tooltipX(W, BOX, W, INSET)).toBe(W - BOX - INSET)
    expect(tooltipX(W + 50, BOX, W, INSET)).toBe(W - BOX - INSET)
  })
})

describe('formatPnl — the tooltip and header P&L label', () => {
  it('signs a gain with + and two decimals', () => {
    expect(formatPnl(36)).toBe('+$36.00')
    expect(formatPnl(12.5)).toBe('+$12.50')
  })

  it('signs a loss with a real minus (U+2212), never a hyphen', () => {
    expect(formatPnl(-12.5)).toBe('−$12.50')
    expect(formatPnl(-12.5)).not.toContain('-')
  })

  it('treats exactly zero as a gain', () => {
    expect(formatPnl(0)).toBe('+$0.00')
  })

  it('always renders two decimal places, even for whole dollars', () => {
    expect(formatPnl(100)).toBe('+$100.00')
    expect(formatPnl(-100)).toBe('−$100.00')
  })

  it('formats large values with thousands separators', () => {
    expect(formatPnl(1234.5)).toBe('+$1,234.50')
  })
})

// Opened 14:00Z, four samples 10 minutes apart (latest = "now" at 14:30Z), scheduled
// to close at 15:00Z — 30 minutes of "rest of session" still ahead of "now".
function timeSeries(...pnls: number[]): Point[] {
  return pnls.map((pnl, i) => ({
    timestamp: `2026-01-15T14:${String(i * 10).padStart(2, '0')}:00Z`,
    pnl,
  }))
}
const AUTO_CLOSE = '2026-01-15T15:00:00Z'

describe('timeChartGeometry — the x-axis is the session clock, not sample index', () => {
  it('spans from the first real sample to the scheduled close, not just to "now"', () => {
    const g = timeChartGeometry(timeSeries(0, 10, 5, 20), AUTO_CLOSE, W, H, PAD)!
    expect(g.x(new Date('2026-01-15T14:00:00Z').getTime())).toBeCloseTo(0, 5)
    expect(g.x(new Date(AUTO_CLOSE).getTime())).toBeCloseTo(W, 5)
  })

  it('puts "now" strictly before the scheduled close when time remains', () => {
    const g = timeChartGeometry(timeSeries(0, 10, 5, 20), AUTO_CLOSE, W, H, PAD)!
    expect(g.sessionEndX).not.toBeNull()
    expect(g.nowX).toBeLessThan(g.sessionEndX!)
  })

  it('has no "rest of session" to shade once the close instant has passed', () => {
    const g = timeChartGeometry(timeSeries(0, 10, 5, 20), '2026-01-15T14:20:00Z', W, H, PAD)!
    // The close (14:20Z) is before the last sample (14:30Z) — already in the past.
    expect(g.sessionEndX).toBeLessThanOrEqual(g.nowX)
  })

  it('falls back to "now" as the domain end with no real scheduled close', () => {
    const g = timeChartGeometry(timeSeries(0, 10, 5, 20), null, W, H, PAD)!
    expect(g.sessionEndX).toBeNull()
    expect(g.x(new Date('2026-01-15T14:30:00Z').getTime())).toBeCloseTo(W, 5)
  })

  it('still spans zero in the y-domain', () => {
    const g = timeChartGeometry(timeSeries(-40, -25, -10, -5), AUTO_CLOSE, W, H, PAD)!
    expect(g.domain.lo).toBe(-40)
    expect(g.domain.hi).toBe(0)
    expect(g.yTicks.some((t) => t.label === '$0')).toBe(true)
  })

  it('lands a time tick every 30 minutes across the session', () => {
    const g = timeChartGeometry(timeSeries(0, 10, 5, 20), AUTO_CLOSE, W, H, PAD)!
    // 14:00Z to 15:00Z on 30-minute ticks: 14:00, 14:30, 15:00 — but the generator
    // starts at the first tick AT OR AFTER the open, so 14:00 and 14:30 and 15:00
    // all qualify.
    expect(g.timeTicks.length).toBe(3)
    const xs = g.timeTicks.map((t) => t.pos)
    expect(xs[0]).toBeCloseTo(0, 5)
    expect(xs[2]).toBeCloseTo(W, 5)
  })

  it('returns null rather than dividing by zero on an unmeasured layout', () => {
    expect(timeChartGeometry(timeSeries(0, 10), AUTO_CLOSE, 0, H, PAD)).toBeNull()
    expect(timeChartGeometry([], AUTO_CLOSE, W, H, PAD)).toBeNull()
  })
})

describe('nearestTimeIndex — snaps to a real sample by its time-based position', () => {
  it('finds the sample whose time-based x is closest to the touch', () => {
    const series = timeSeries(0, 10, 5, 20)
    const g = timeChartGeometry(series, AUTO_CLOSE, W, H, PAD)!
    // Sample 1 (14:10Z) sits at x = (10/60)*W = W/6.
    const x1 = g.x(new Date('2026-01-15T14:10:00Z').getTime())
    expect(nearestTimeIndex(x1, g, series)).toBe(1)
  })

  it('never returns an index outside the series', () => {
    const series = timeSeries(0, 10, 5, 20)
    const g = timeChartGeometry(series, AUTO_CLOSE, W, H, PAD)!
    for (const x of [-500, 0, W, W + 500]) {
      const i = nearestTimeIndex(x, g, series)
      expect(i).toBeGreaterThanOrEqual(0)
      expect(i).toBeLessThanOrEqual(series.length - 1)
    }
  })
})

describe('formatAxisDollar — the y-axis gridline labels', () => {
  it('renders a whole dollar amount with no cents', () => {
    expect(formatAxisDollar(36)).toBe('$36')
    expect(formatAxisDollar(36.4)).toBe('$36')
  })

  it('signs a negative amount with a real minus, never a hyphen', () => {
    expect(formatAxisDollar(-12)).toBe('−$12')
    expect(formatAxisDollar(-12)).not.toContain('-')
  })

  it('renders exactly zero with no sign', () => {
    expect(formatAxisDollar(0)).toBe('$0')
  })
})

describe('formatAxisTime — the 30-minute axis labels, CT, design-compact', () => {
  it('drops the leading zero minutes and uses lowercase a/p', () => {
    // 2026-01-15 is standard time (CST, UTC-6) — no DST ambiguity.
    expect(formatAxisTime(new Date('2026-01-15T15:30:00Z').getTime())).toBe('9:30a')
    expect(formatAxisTime(new Date('2026-01-15T18:00:00Z').getTime())).toBe('12p')
  })
})
