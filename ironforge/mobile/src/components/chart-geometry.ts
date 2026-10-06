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

export interface AxisTick {
  /** Pixel position along the axis. */
  pos: number
  label: string
}

export interface TimeGeometry {
  /** Pixel x for a real timestamp (ms since epoch) — NOT evenly spaced by index;
   *  a gap in real samples is a gap on screen, same as the design's own
   *  `drawTradeChart`. */
  x: (ms: number) => number
  y: (v: number) => number
  zeroY: number
  domain: { lo: number; hi: number }
  /** Polyline through the real samples only — never interpolated past "now". */
  points: string
  /** Pixel x of the last real sample ("now"). */
  nowX: number
  /** Pixel x of the session's expected close, or null when unknown. */
  sessionEndX: number | null
  /** "Nice" dollar gridlines (10.4 design `drawTradeChart`'s 1/2/2.5/5×10ⁿ step). */
  yTicks: AxisTick[]
  /** One label every 30 minutes across the session, CT-formatted like the design
   *  ("9:30a", "10a", "12:30p"). */
  timeTicks: AxisTick[]
}

/**
 * Time-based geometry for the live-trade chart (10.4 design `drawTradeChart`) — the x-axis
 * is the session's actual clock, not sample index, so the plotted line sits where it really
 * happened and the remaining time to the scheduled close can be shaded. Falls back to `null`
 * exactly like `chartGeometry` when there is nothing to lay out.
 */
export function timeChartGeometry(
  series: Point[],
  autoCloseAt: string | null | undefined,
  width: number,
  height: number,
  padY: number,
): TimeGeometry | null {
  if (!series.length || width <= 0 || height <= padY * 2) return null

  const ts = series.map((p) => new Date(p.timestamp).getTime())
  if (ts.some((t) => Number.isNaN(t))) return null
  const t0 = ts[0]
  const tNow = ts[ts.length - 1]
  const closeMs = autoCloseAt ? new Date(autoCloseAt).getTime() : NaN
  const tEnd = !Number.isNaN(closeMs) && closeMs > tNow ? closeMs : tNow
  const span = Math.max(1, tEnd - t0)

  const x = (ms: number) => clamp(((ms - t0) / span) * width, 0, width)

  const values = series.map((p) => p.pnl)
  const lo = Math.min(0, ...values)
  const hi = Math.max(0, ...values)
  const ySpan = hi - lo || 1
  const y = (v: number) => padY + (1 - (v - lo) / ySpan) * (height - padY * 2)

  return {
    x,
    y,
    zeroY: y(0),
    domain: { lo, hi },
    points: series.map((p, i) => `${x(ts[i]).toFixed(2)},${y(p.pnl).toFixed(2)}`).join(' '),
    nowX: x(tNow),
    sessionEndX: !Number.isNaN(closeMs) && closeMs > t0 ? x(closeMs) : null,
    yTicks: niceDollarTicks(lo, hi).map((v) => ({ pos: y(v), label: formatAxisDollar(v) })),
    timeTicks: thirtyMinuteTicks(t0, tEnd).map((ms) => ({ pos: x(ms), label: formatAxisTime(ms) })),
  }
}

/** Index of the real sample nearest a touch, snapping by its TIME-based pixel
 *  position rather than assuming even spacing. */
export function nearestTimeIndex(touchX: number, geom: TimeGeometry, series: Point[]): number {
  let best = 0
  let bestDist = Infinity
  series.forEach((p, i) => {
    const d = Math.abs(geom.x(new Date(p.timestamp).getTime()) - touchX)
    if (d < bestDist) {
      bestDist = d
      best = i
    }
  })
  return best
}

/** The design's own step rule (`drawTradeChart`): the smallest of 1/2/2.5/5×10ⁿ
 *  at or above half the plotted span, so gridlines land on round dollar amounts. */
function niceStep(span: number): number {
  const raw = span / 2.5 || 1
  const pow = Math.pow(10, Math.floor(Math.log10(raw)))
  const candidates = [1, 2, 2.5, 5, 10].map((m) => m * pow)
  return candidates.find((v) => v >= raw) ?? candidates[candidates.length - 1]
}

function niceDollarTicks(lo: number, hi: number): number[] {
  const step = niceStep(hi - lo || 1)
  const ticks: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) ticks.push(Math.round(v * 100) / 100)
  return ticks
}

function thirtyMinuteTicks(startMs: number, endMs: number): number[] {
  const STEP = 30 * 60_000
  const ticks: number[] = []
  for (let t = Math.ceil(startMs / STEP) * STEP; t <= endMs; t += STEP) ticks.push(t)
  return ticks
}

/** "$36" / "−$12" — whole dollars, real minus, matching the design's gridline labels. */
export function formatAxisDollar(v: number): string {
  const sign = v < 0 ? '−' : ''
  return `${sign}$${Math.round(Math.abs(v))}`
}

/** "9:30a" / "12p" — the design's own compact CT clock label for a 30-minute tick. */
export function formatAxisTime(ms: number): string {
  const d = new Date(ms)
  const label = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/Chicago' })
  return label.replace(':00', '').replace(' AM', 'a').replace(' PM', 'p')
}

export function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v))
}

/**
 * Left-edge x for the touch tooltip box — centered on the touched point, but
 * slid inward near either edge so it never clips outside the chart. Pure so
 * the three cases (left edge, right edge, centered) are covered by a test
 * instead of eyeballed on a phone.
 */
export function tooltipX(pointX: number, boxWidth: number, chartWidth: number, inset: number): number {
  const centered = pointX - boxWidth / 2
  return clamp(centered, inset, Math.max(inset, chartWidth - boxWidth - inset))
}

/** "+$36.00" / "−$12.50" — a real minus (U+2212), not a hyphen, and always two
 *  decimals, so the tooltip and header never print a bare unsigned number. */
export function formatPnl(v: number): string {
  const sign = v >= 0 ? '+' : '−'
  return `${sign}$${Math.abs(v).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}
