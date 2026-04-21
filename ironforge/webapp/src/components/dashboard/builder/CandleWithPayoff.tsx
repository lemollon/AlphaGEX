'use client'

/**
 * CandleWithPayoff — unified IC visualization matching the SpreadWorks layout.
 *
 * Single SVG canvas, shared price Y-axis:
 *   • Left ~70% : intraday candle chart + volume histogram
 *   • Right ~20%: sideways payoff curve (P&L on X-axis, price on Y-axis —
 *                 same price scale as candles)
 *   • Strike dashed lines span BOTH regions so operator sees where the
 *     market has traded AND where the payoff curve crosses at that strike,
 *     on the same horizontal row.
 *   • Breakeven ticks + "BE $XXX" labels on the right edge
 *   • Current price badge at the candle/payoff boundary
 *   • Current unrealized P&L badge floating in the payoff region at spot's Y
 *
 * Props come from the existing /api/[bot]/builder/{snapshot,candles}
 * endpoints — no new data fetches.
 */
import { useMemo } from 'react'

export interface Candle {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface PnlPoint {
  price: number
  pnl: number
}

interface CandleWithPayoffProps {
  candles: Candle[] | null | undefined
  spotPrice?: number | null
  strikes?: {
    putLong?: number | null
    putShort?: number | null
    callShort?: number | null
    callLong?: number | null
  } | null
  pnlCurve?: PnlPoint[] | null
  breakevens?: { lower: number | null; upper: number | null } | null
  /** Current unrealized P&L in dollars, for the floating "Now: +$X" badge */
  currentPnl?: number | null
  /** Current unrealized P&L as a percent of credit received */
  currentPnlPct?: number | null
  height?: number
}

// Layout constants for the viewBox (1200 × height)
const VB_W = 1200
const AXIS_LEFT_PAD = 56                  // price axis labels on far left
const CANDLE_X0 = AXIS_LEFT_PAD
const CANDLE_X1 = 860                     // candle region right edge
const SPOT_BADGE_W = 62                   // gap between candles and payoff
const PAYOFF_X0 = CANDLE_X1 + SPOT_BADGE_W
const PAYOFF_X1 = VB_W - 86               // leaves room for BE labels
const RIGHT_LABEL_X = VB_W - 82
const TOP_PAD = 14
const BOTTOM_PAD = 32                     // date labels
const VOLUME_H = 36

const DEFAULT_CANDLE_SPACING = 8

function priceToY(price: number, minP: number, maxP: number, plotH: number): number {
  if (maxP === minP) return plotH / 2
  return TOP_PAD + (1 - (price - minP) / (maxP - minP)) * plotH
}

export default function CandleWithPayoff({
  candles,
  spotPrice,
  strikes,
  pnlCurve,
  breakevens,
  currentPnl,
  currentPnlPct,
  height = 440,
  // No need to configure candle spacing externally — layout is SpreadWorks-style.
}: CandleWithPayoffProps) {
  const data = useMemo(() => {
    const hasCandles = candles && candles.length > 0
    if (!hasCandles && !(pnlCurve && pnlCurve.length)) return null

    // Build the Y-axis price range from candles + strikes + breakevens + pnlCurve kinks
    const pricePoints: number[] = []
    if (hasCandles) {
      for (const c of candles!) {
        pricePoints.push(c.high, c.low)
      }
    }
    if (strikes) {
      for (const v of [strikes.putLong, strikes.putShort, strikes.callShort, strikes.callLong]) {
        if (v != null && Number.isFinite(v)) pricePoints.push(v)
      }
    }
    if (breakevens) {
      for (const v of [breakevens.lower, breakevens.upper]) {
        if (v != null && Number.isFinite(v)) pricePoints.push(v)
      }
    }
    if (pnlCurve) {
      for (const p of pnlCurve) pricePoints.push(p.price)
    }
    if (spotPrice != null) pricePoints.push(spotPrice)
    if (!pricePoints.length) return null
    let minP = Math.min(...pricePoints)
    let maxP = Math.max(...pricePoints)
    // 5% padding so strikes don't sit flush at the edges
    const pricePad = Math.max((maxP - minP) * 0.05, 0.5)
    minP -= pricePad
    maxP += pricePad

    const plotH = height - TOP_PAD - BOTTOM_PAD
    const pToY = (p: number) => priceToY(p, minP, maxP, plotH)

    // Candle layout — fit as many as possible in the candle region without
    // ever entering the payoff region.
    const candleRegionW = CANDLE_X1 - CANDLE_X0
    const maxCandles = Math.floor(candleRegionW / DEFAULT_CANDLE_SPACING)
    const visible = hasCandles ? candles!.slice(-maxCandles) : []
    const barWidth = Math.max(2, Math.round(DEFAULT_CANDLE_SPACING * 0.67))
    const maxVol = hasCandles ? Math.max(...visible.map((c) => c.volume || 0), 1) : 1

    const bars = visible.map((c, i) => {
      const centerX = CANDLE_X0 + i * DEFAULT_CANDLE_SPACING
      const x = centerX - barWidth / 2
      const isUp = c.close >= c.open
      const color = isUp ? '#26a69a' : '#ef5350'
      const bodyTop = pToY(Math.max(c.open, c.close))
      const bodyBottom = pToY(Math.min(c.open, c.close))
      const bodyHeight = Math.max(bodyBottom - bodyTop, 1)
      const wickTop = pToY(c.high)
      const wickBottom = pToY(c.low)
      const volH = ((c.volume || 0) / maxVol) * VOLUME_H
      const volY = height - BOTTOM_PAD - volH
      return { x, centerX, bodyTop, bodyHeight, wickTop, wickBottom, color, volH, volY, volColor: isUp ? '#26a69a44' : '#ef535044', time: c.time }
    })
    const lastCandleX = bars.length ? bars[bars.length - 1].centerX : null

    // Price gridlines
    const priceRange = maxP - minP
    const gridStep = priceRange > 60 ? 10 : priceRange > 30 ? 5 : priceRange > 15 ? 2 : priceRange > 5 ? 1 : 0.5
    const gridStart = Math.ceil(minP / gridStep) * gridStep
    const priceTicks: Array<{ price: number; y: number }> = []
    for (let p = gridStart; p <= maxP; p += gridStep) {
      priceTicks.push({ price: p, y: pToY(p) })
    }

    // Time labels (CT), spaced to avoid the payoff region
    const timeLabels: Array<{ x: number; label: string }> = []
    const labelEvery = Math.max(8, Math.round(16 * DEFAULT_CANDLE_SPACING / DEFAULT_CANDLE_SPACING))
    for (let i = 0; i < visible.length; i += labelEvery) {
      const c = visible[i]
      const labelX = CANDLE_X0 + i * DEFAULT_CANDLE_SPACING
      if (c && c.time && labelX < CANDLE_X1 - 20) {
        const d = new Date(c.time)
        const label = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/Chicago' })
        timeLabels.push({ x: labelX, label })
      }
    }

    // Payoff math — convert pnlCurve to the sideways orientation. We need
    // the P&L domain to build the zero-line and the X scaling.
    const hasPayoff = pnlCurve && pnlCurve.length > 0
    let payoffPolyline = ''
    let payoffAreaProfit = ''
    let payoffAreaLoss = ''
    let zeroLineX = PAYOFF_X0
    let pnlMin = 0
    let pnlMax = 0
    let nowPnlX: number | null = null
    if (hasPayoff) {
      const pnls = pnlCurve!.map((p) => p.pnl)
      pnlMin = Math.min(...pnls, 0)
      pnlMax = Math.max(...pnls, 0)
      const pnlRange = pnlMax - pnlMin || 1
      const payoffW = PAYOFF_X1 - PAYOFF_X0
      const pnlToX = (pnl: number) => PAYOFF_X0 + ((pnl - pnlMin) / pnlRange) * payoffW
      zeroLineX = pnlToX(0)
      // Only include points within our Y-range to avoid polyline spikes
      // near the padded edges.
      const pts = pnlCurve!
        .filter((p) => p.price >= minP && p.price <= maxP)
        .map((p) => `${pnlToX(p.pnl).toFixed(1)},${pToY(p.price).toFixed(1)}`)
      payoffPolyline = `M${pts.join('L')}`
      // Fills are polygons closed back to the zero-line at the top and bottom
      if (pts.length > 1) {
        const firstY = pnlCurve![0].price >= minP && pnlCurve![0].price <= maxP
          ? pToY(pnlCurve![0].price)
          : pToY(minP)
        const lastY = pnlCurve![pnlCurve!.length - 1].price >= minP && pnlCurve![pnlCurve!.length - 1].price <= maxP
          ? pToY(pnlCurve![pnlCurve!.length - 1].price)
          : pToY(maxP)
        // Profit region = where curve is to the right of zero-line (x > zeroLineX)
        // Loss region = to the left (x < zeroLineX).
        // We use one polygon clipped by a vertical rect at zeroLineX for each.
        payoffAreaProfit = `M${zeroLineX.toFixed(1)},${firstY.toFixed(1)} L${pts.join('L')} L${zeroLineX.toFixed(1)},${lastY.toFixed(1)} Z`
        payoffAreaLoss = payoffAreaProfit
      }
      // Current P&L badge X position in the payoff region
      if (currentPnl != null) nowPnlX = pnlToX(currentPnl)
    }

    return {
      minP, maxP, plotH, pToY, bars, lastCandleX, priceTicks, timeLabels,
      hasPayoff, payoffPolyline, payoffAreaProfit, payoffAreaLoss,
      zeroLineX, pnlMin, pnlMax, nowPnlX,
      barWidth,
    }
  }, [candles, strikes, spotPrice, pnlCurve, breakevens, currentPnl, height])

  if (!data) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-6 text-center" style={{ height }}>
        <p className="text-forge-muted text-sm mt-8">No chart data yet — load during market hours.</p>
      </div>
    )
  }

  const {
    minP, maxP, pToY, bars, lastCandleX, priceTicks, timeLabels,
    hasPayoff, payoffPolyline, payoffAreaProfit, payoffAreaLoss,
    zeroLineX, pnlMin, pnlMax, nowPnlX, barWidth,
  } = data

  const spotY = spotPrice != null ? pToY(spotPrice) : null

  // Strike lines — annotated labels on the LEFT edge (inside AXIS_LEFT_PAD
  // region) so they match the SpreadWorks example. Colors: green for longs,
  // red for shorts.
  const strikeEntries: Array<{ price: number; y: number; color: string; label: string }> = []
  if (strikes) {
    const entries: Array<[number | null | undefined, string]> = [
      [strikes.callLong, '#22c55e'],
      [strikes.callShort, '#ef4444'],
      [strikes.putShort, '#ef4444'],
      [strikes.putLong, '#22c55e'],
    ]
    for (const [p, color] of entries) {
      if (p != null && p >= minP && p <= maxP) {
        strikeEntries.push({ price: p, y: pToY(p), color, label: `$${p.toFixed(2).replace(/\.00$/, '')}` })
      }
    }
  }

  // Breakeven ticks on the right edge
  const beEntries: Array<{ price: number; y: number }> = []
  if (breakevens) {
    if (breakevens.lower != null && breakevens.lower >= minP && breakevens.lower <= maxP) {
      beEntries.push({ price: breakevens.lower, y: pToY(breakevens.lower) })
    }
    if (breakevens.upper != null && breakevens.upper >= minP && breakevens.upper <= maxP) {
      beEntries.push({ price: breakevens.upper, y: pToY(breakevens.upper) })
    }
  }

  // P&L badge label
  const pnlBadge = currentPnl != null
    ? `Now: ${currentPnl >= 0 ? '+' : ''}$${Math.round(currentPnl).toLocaleString()}${
        currentPnlPct != null ? ` (${currentPnlPct >= 0 ? '+' : ''}${currentPnlPct.toFixed(1)}%)` : ''
      }`
    : null
  const badgeIsGain = (currentPnl ?? 0) >= 0

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 overflow-hidden">
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${VB_W} ${height}`}
        preserveAspectRatio="none"
        style={{ display: 'block', background: '#0a0a1a' }}
      >
        {/* Clip paths for payoff profit/loss fills (sideways) */}
        <defs>
          <clipPath id="payoff-profit-clip">
            <rect x={zeroLineX} y={0} width={Math.max(0, PAYOFF_X1 - zeroLineX)} height={height} />
          </clipPath>
          <clipPath id="payoff-loss-clip">
            <rect x={PAYOFF_X0} y={0} width={Math.max(0, zeroLineX - PAYOFF_X0)} height={height} />
          </clipPath>
        </defs>

        {/* Full-width price grid */}
        {priceTicks.map((t, i) => (
          <g key={`pt-${i}`}>
            <line x1={AXIS_LEFT_PAD} y1={t.y} x2={PAYOFF_X1} y2={t.y} stroke="#14142b" strokeWidth="0.5" />
            <text x={AXIS_LEFT_PAD - 6} y={t.y + 3} textAnchor="end" fill="#555" fontSize="9" fontFamily="monospace">
              ${t.price}
            </text>
          </g>
        ))}

        {/* Strike horizontal lines — span candle AND payoff regions */}
        {strikeEntries.map((s, i) => (
          <g key={`strike-${i}`}>
            <line
              x1={AXIS_LEFT_PAD}
              y1={s.y}
              x2={PAYOFF_X1}
              y2={s.y}
              stroke={s.color}
              strokeWidth="1"
              strokeDasharray="6,4"
              opacity="0.7"
            />
            <text
              x={AXIS_LEFT_PAD + 6}
              y={s.y - 3}
              fill={s.color}
              fontSize="10"
              fontWeight="600"
              fontFamily="monospace"
            >
              {s.label}
            </text>
          </g>
        ))}

        {/* Volume bars (candle region only) */}
        {bars.map((b, i) => (
          <rect key={`v-${i}`} x={b.x} y={b.volY} width={barWidth} height={b.volH} fill={b.volColor} />
        ))}

        {/* Candles */}
        {bars.map((b, i) => (
          <g key={`c-${i}`}>
            <line x1={b.centerX} y1={b.wickTop} x2={b.centerX} y2={b.wickBottom} stroke={b.color} strokeWidth="1" />
            <rect x={b.x} y={b.bodyTop} width={barWidth} height={b.bodyHeight} fill={b.color} />
          </g>
        ))}

        {/* Current-price vertical dashed line (blue) at the last candle */}
        {lastCandleX != null && (
          <line
            x1={lastCandleX}
            y1={TOP_PAD}
            x2={lastCandleX}
            y2={height - BOTTOM_PAD}
            stroke="#448aff"
            strokeWidth="1"
            strokeDasharray="3,3"
            opacity="0.6"
          />
        )}

        {/* Spot price badge in the gap between candle and payoff regions */}
        {spotPrice != null && spotY != null && (
          <g>
            <rect
              x={CANDLE_X1 + 2}
              y={spotY - 9}
              width={SPOT_BADGE_W - 4}
              height={18}
              rx={3}
              fill="#448aff"
            />
            <text
              x={CANDLE_X1 + SPOT_BADGE_W / 2}
              y={spotY + 4}
              textAnchor="middle"
              fill="#fff"
              fontSize="10"
              fontWeight="700"
              fontFamily="monospace"
            >
              ${spotPrice.toFixed(2)}
            </text>
          </g>
        )}

        {/* ── Sideways payoff region ─────────────────────────────── */}
        {hasPayoff && (
          <>
            {/* Profit fill (curve right of zero-line, green) */}
            <path d={payoffAreaProfit} fill="rgba(34,197,94,0.22)" clipPath="url(#payoff-profit-clip)" />
            {/* Loss fill (curve left of zero-line, red) */}
            <path d={payoffAreaLoss} fill="rgba(239,68,68,0.22)" clipPath="url(#payoff-loss-clip)" />
            {/* Zero-line reference */}
            <line
              x1={zeroLineX}
              y1={TOP_PAD}
              x2={zeroLineX}
              y2={height - BOTTOM_PAD}
              stroke="#64748b"
              strokeWidth="1"
              strokeDasharray="4,3"
              opacity="0.5"
            />
            {/* Payoff polyline stroke */}
            <path d={payoffPolyline} fill="none" stroke="#3b82f6" strokeWidth="2" />
            {/* P&L axis min/max labels below the payoff */}
            <text x={PAYOFF_X0 + 2} y={height - BOTTOM_PAD + 12} fill="#64748b" fontSize="9" fontFamily="monospace">
              {pnlMin >= 0 ? '' : '-'}${Math.round(Math.abs(pnlMin)).toLocaleString()}
            </text>
            <text x={PAYOFF_X1 - 2} y={height - BOTTOM_PAD + 12} textAnchor="end" fill="#64748b" fontSize="9" fontFamily="monospace">
              +${Math.round(pnlMax).toLocaleString()}
            </text>
            <text
              x={zeroLineX}
              y={height - BOTTOM_PAD + 12}
              textAnchor="middle"
              fill="#64748b"
              fontSize="9"
              fontFamily="monospace"
            >
              P&L
            </text>
          </>
        )}

        {/* Breakeven tick + label on the right edge (yellow) */}
        {beEntries.map((be, i) => (
          <g key={`be-${i}`}>
            <line
              x1={PAYOFF_X1 - 4}
              y1={be.y}
              x2={PAYOFF_X1 + 10}
              y2={be.y}
              stroke="#facc15"
              strokeWidth="2"
            />
            <text x={RIGHT_LABEL_X} y={be.y - 3} fill="#facc15" fontSize="10" fontWeight="700" fontFamily="monospace">
              BE
            </text>
            <text x={RIGHT_LABEL_X} y={be.y + 10} fill="#facc15" fontSize="9" fontFamily="monospace">
              ${be.price.toFixed(2).replace(/\.00$/, '')}
            </text>
          </g>
        ))}

        {/* "Now: +$XXX (+X.X%)" P&L badge at the current spot's Y in the payoff region */}
        {nowPnlX != null && spotY != null && pnlBadge && (
          <g>
            <rect
              x={Math.min(Math.max(nowPnlX - 55, PAYOFF_X0 + 2), PAYOFF_X1 - 112)}
              y={spotY - 10}
              width={110}
              height={20}
              rx={4}
              fill={badgeIsGain ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)'}
              stroke={badgeIsGain ? '#22c55e' : '#ef4444'}
              strokeWidth="1"
            />
            <text
              x={Math.min(Math.max(nowPnlX, PAYOFF_X0 + 57), PAYOFF_X1 - 57)}
              y={spotY + 4}
              textAnchor="middle"
              fill={badgeIsGain ? '#86efac' : '#fca5a5'}
              fontSize="10"
              fontWeight="700"
              fontFamily="monospace"
            >
              {pnlBadge}
            </text>
          </g>
        )}

        {/* Time labels (candle region bottom) */}
        {timeLabels.map((tl, i) => (
          <text key={`tl-${i}`} x={tl.x} y={height - 10} fill="#555" fontSize="9" fontFamily="monospace">
            {tl.label}
          </text>
        ))}

        {/* Border around the full chart */}
        <rect
          x={AXIS_LEFT_PAD}
          y={TOP_PAD}
          width={PAYOFF_X1 - AXIS_LEFT_PAD}
          height={height - TOP_PAD - BOTTOM_PAD}
          fill="none"
          stroke="#1f1f38"
        />
        {/* Vertical separator between candle and payoff regions */}
        <line
          x1={PAYOFF_X0 - SPOT_BADGE_W}
          y1={TOP_PAD}
          x2={PAYOFF_X0 - SPOT_BADGE_W}
          y2={height - BOTTOM_PAD}
          stroke="#1f1f38"
          strokeWidth="0.5"
        />
        <line
          x1={PAYOFF_X0}
          y1={TOP_PAD}
          x2={PAYOFF_X0}
          y2={height - BOTTOM_PAD}
          stroke="#1f1f38"
          strokeWidth="0.5"
        />
      </svg>
    </div>
  )
}
