/**
 * The maths behind the intraday P&L chart, extracted so the one rule that matters can be
 * tested.
 *
 * THE RULE: the y-domain ALWAYS includes zero. A P&L chart scaled to its own min/max can
 * render a trade that is down $40 and recovering to down $10 as a confidently rising
 * line with no breakeven marker in frame — it looks like a winner. Every other detail
 * here is presentation; this one is the difference between informing someone and
 * misleading them about their own money.
 */
export interface Point {
  timestamp: string
  pnl: number
}

export interface Geometry {
  /** Pixel x for sample i. */
  x: (i: number) => number
  /** Pixel y for a P&L value. */
  y: (v: number) => number
  /** Pixel y of the breakeven line. */
  zeroY: number
  /** Low and high of the plotted domain — always spanning zero. */
  domain: { lo: number; hi: number }
  points: string
}

export function chartGeometry(
  series: Point[],
  width: number,
  height: number,
  padY: number,
): Geometry | null {
  if (!series.length || width <= 0 || height <= padY * 2) return null

  const values = series.map((p) => p.pnl)
  // Zero is seeded into both ends of the domain, not clamped afterwards.
  const lo = Math.min(0, ...values)
  const hi = Math.max(0, ...values)
  // A flat series at exactly zero has no span; 1 keeps the divide finite and draws a
  // straight line on the breakeven, which is the truth.
  const span = hi - lo || 1

  const x = (i: number) => (series.length === 1 ? width / 2 : (i / (series.length - 1)) * width)
  const y = (v: number) => padY + (1 - (v - lo) / span) * (height - padY * 2)

  return {
    x,
    y,
    zeroY: y(0),
    domain: { lo, hi },
    points: series.map((p, i) => `${x(i).toFixed(2)},${y(p.pnl).toFixed(2)}`).join(' '),
  }
}

/** Index of the sample nearest a touch at pixel x. Never interpolates a value. */
export function nearestIndex(x: number, width: number, n: number): number {
  if (width <= 0 || n < 2) return 0
  return clamp(Math.round((x / width) * (n - 1)), 0, n - 1)
}

export function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v))
}
