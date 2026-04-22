/**
 * Payoff-panel shape helpers.
 * Ported verbatim from spreadworks/frontend/src/utils/payoffShape.js.
 *
 * Payoff panel is oriented sideways:
 *   Y-axis = price (shared with candle chart)
 *   X-axis = P&L magnitude
 *   Zero line at X=220 (right edge, touching candle chart divider)
 *   Profit grows LEFT from X=220 (toward X=20)
 *   Loss grows RIGHT from X=220 (toward X=280)
 */

export interface PnlPoint {
  price: number
  pnl: number
}

export interface PayoffSvgPoint {
  x: number
  y: number
  pnl: number
}

/**
 * Convert pnl_curve [{price, pnl}] to SVG points for the payoff panel.
 * profit → x grows smaller (left of zero-line); loss → x grows larger.
 */
export function pnlCurveToPoints(
  pnlCurve: PnlPoint[] | null | undefined,
  priceToYFn: (price: number) => number,
  maxAbsPnl: number,
  viewWidth = 280,
  zeroX = 220,
): PayoffSvgPoint[] {
  if (!pnlCurve || pnlCurve.length === 0) return []
  const scale = maxAbsPnl > 0 ? 160 / maxAbsPnl : 1

  return pnlCurve.map(({ price, pnl }) => {
    const y = priceToYFn(price)
    let x: number
    if (pnl >= 0) {
      x = zeroX - pnl * scale // profit grows left
      x = Math.max(x, 20)
    } else {
      x = zeroX + Math.abs(pnl) * scale // loss grows right
      x = Math.min(x, viewWidth - 5)
    }
    return { x, y, pnl }
  })
}

/**
 * Smooth SVG path from points via Catmull-Rom → cubic Bézier (tension 0.3).
 * Matches SpreadWorks exactly so the curve reads identically.
 */
export function buildSmoothPath(points: PayoffSvgPoint[]): string {
  if (points.length < 2) return ''
  if (points.length === 2) {
    return `M${points[0].x.toFixed(1)},${points[0].y.toFixed(1)} L${points[1].x.toFixed(1)},${points[1].y.toFixed(1)}`
  }

  let d = `M${points[0].x.toFixed(1)},${points[0].y.toFixed(1)}`

  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(i - 1, 0)]
    const p1 = points[i]
    const p2 = points[i + 1]
    const p3 = points[Math.min(i + 2, points.length - 1)]

    const tension = 0.3
    const cp1x = p1.x + (p2.x - p0.x) * tension
    const cp1y = p1.y + (p2.y - p0.y) * tension
    const cp2x = p2.x - (p3.x - p1.x) * tension
    const cp2y = p2.y - (p3.y - p1.y) * tension

    d += ` C${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`
  }

  return d
}

/** Closed fill path back to the zero-line (used for area fills). */
export function buildFillPath(points: PayoffSvgPoint[], zeroX = 220): string {
  if (points.length < 2) return ''
  const first = points[0]
  const last = points[points.length - 1]
  const curvePart = buildSmoothPath(points)
  return `${curvePart} L${zeroX},${last.y.toFixed(1)} L${zeroX},${first.y.toFixed(1)} Z`
}

/**
 * Straight-line (polyline) path from points. Use this for mathematically
 * exact expiration P&L curves — an Iron Condor at expiration is piecewise
 * linear with 4 hard kinks (one per strike), and the smoothed Catmull-Rom
 * path visually distorts those kinks into rounded curves.
 *
 * No tension, no Bézier handles — just `M` + `L` per vertex.
 */
export function buildLinearPath(points: PayoffSvgPoint[]): string {
  if (points.length < 2) return ''
  let d = `M${points[0].x.toFixed(1)},${points[0].y.toFixed(1)}`
  for (let i = 1; i < points.length; i++) {
    d += ` L${points[i].x.toFixed(1)},${points[i].y.toFixed(1)}`
  }
  return d
}

/** Closed fill path (straight-line) back to the zero-line. */
export function buildLinearFillPath(points: PayoffSvgPoint[], zeroX = 220): string {
  if (points.length < 2) return ''
  const first = points[0]
  const last = points[points.length - 1]
  const poly = buildLinearPath(points)
  return `${poly} L${zeroX},${last.y.toFixed(1)} L${zeroX},${first.y.toFixed(1)} Z`
}

/** Split into profit/loss point arrays for separate fills. */
export function splitProfitLoss(points: PayoffSvgPoint[]): {
  profitPoints: PayoffSvgPoint[]
  lossPoints: PayoffSvgPoint[]
} {
  const profitPoints: PayoffSvgPoint[] = []
  const lossPoints: PayoffSvgPoint[] = []
  for (const pt of points) {
    if (pt.pnl >= 0) profitPoints.push(pt)
    else lossPoints.push(pt)
  }
  return { profitPoints, lossPoints }
}
