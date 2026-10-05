import type { AccountPoint } from '@/live/account-series'

/**
 * Geometry for the Forge hero chart — an ACCOUNT VALUE line, not a P&L line.
 *
 * Deliberately different from chart-geometry.ts's rule: that chart must always
 * span zero because it plots profit/loss, where zero is "broke even" and
 * cropping it out can make a loser look like a winner. This one plots a
 * dollar BALANCE, which is never near zero for a funded account — forcing
 * zero into the domain here would flatten the real movement in the line to a
 * sliver at the top of the chart. The domain is the series' own min/max with
 * a little headroom, same as the app.html prototype's drawChart().
 */
export interface AccountGeometry {
  x: (i: number) => number
  y: (v: number) => number
  domain: { lo: number; hi: number }
  points: string
}

export function accountChartGeometry(
  series: AccountPoint[],
  width: number,
  height: number,
  padY: number,
): AccountGeometry | null {
  if (series.length < 2 || width <= 0 || height <= padY * 2) return null

  const values = series.map((p) => p.v)
  const lo0 = Math.min(...values)
  const hi0 = Math.max(...values)
  const pad = (hi0 - lo0) * 0.12 || Math.max(1, Math.abs(hi0) * 0.02)
  const lo = lo0 - pad
  const hi = hi0 + pad
  const span = hi - lo || 1

  const t0 = series[0].t
  const t1 = series[series.length - 1].t
  const tSpan = t1 - t0 || 1

  const x = (i: number) => ((series[i].t - t0) / tSpan) * width
  const y = (v: number) => padY + (1 - (v - lo) / span) * (height - padY * 2)

  return {
    x,
    y,
    domain: { lo, hi },
    points: series.map((p, i) => `${x(i).toFixed(2)},${y(p.v).toFixed(2)}`).join(' '),
  }
}

/** Index of the sample nearest a touch at pixel x — never interpolates a value
 *  the series did not actually print (same rule as chart-geometry.ts). */
export function nearestAccountIndex(x: number, width: number, n: number): number {
  if (width <= 0 || n < 2) return 0
  const i = Math.round((x / width) * (n - 1))
  return Math.max(0, Math.min(n - 1, i))
}
