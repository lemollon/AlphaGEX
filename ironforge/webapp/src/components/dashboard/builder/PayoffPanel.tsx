'use client'

/**
 * PayoffPanel — ported verbatim from
 * spreadworks/frontend/src/components/PayoffPanel.jsx.
 *
 * Sideways payoff diagram panel that sits to the RIGHT of the candle chart.
 *   Y-axis = price (shared with candle chart via priceToY + min/max props)
 *   X-axis = P&L magnitude
 *   Zero line at X=220 (right edge, touching candle chart divider)
 *   Profit grows LEFT from X=220
 *   Loss grows RIGHT from X=220
 *
 * Features:
 *   - Catmull-Rom → cubic Bézier smooth path (same math as SpreadWorks)
 *   - Gradient fills (profit fades solid→transparent moving away from zero,
 *     loss fades transparent→solid moving away from zero)
 *   - Strike horizontal lines continue across (opacity 0.4, dimmer than
 *     the candle panel's 0.7) — same Y coordinates as candle panel
 *   - Spot price horizontal blue line + small blue-tint badge on right edge
 *   - BE yellow ticks straddling the zero-line at each breakeven price
 *   - Floating "Now: +$X (+X.X%)" badge on LEFT of the panel at spot's Y
 *   - Strike $price labels on right edge
 */
import { useMemo } from 'react'
import { priceToY } from '@/lib/price-scale'
import {
  pnlCurveToPoints,
  buildSmoothPath,
  buildFillPath,
  splitProfitLoss,
  type PnlPoint,
  type PayoffSvgPoint,
} from '@/lib/payoff-shape'

const VIEW_WIDTH = 280
const ZERO_X = 220

interface PayoffPanelProps {
  pnlCurve: PnlPoint[] | null | undefined
  minPrice: number
  maxPrice: number
  height: number
  strikes?: {
    longPutStrike?: number | null
    longCallStrike?: number | null
    shortPutStrike?: number | null
    shortCallStrike?: number | null
  } | null
  spotPrice?: number | null
  maxProfit?: number | null
  maxLoss?: number | null
  breakevens?: { lower?: number | null; upper?: number | null } | null
}

function formatDollarPnl(pnl: number): string {
  const rounded = Math.round(pnl)
  const abs = Math.abs(rounded).toLocaleString()
  return rounded >= 0 ? `+$${abs}` : `-$${abs}`
}
function formatSignedPct(pct: number): string {
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`
}

export default function PayoffPanel({
  pnlCurve,
  minPrice,
  maxPrice,
  height,
  strikes,
  spotPrice,
  maxProfit,
  maxLoss,
  breakevens,
}: PayoffPanelProps) {
  const plotH = height - 10 - 28 // match candle chart TOP_PAD + BOTTOM_PAD
  const topPad = 10

  const pToY = (p: number) => topPad + priceToY(p, minPrice, maxPrice, plotH)

  const paths = useMemo(() => {
    if (!pnlCurve || pnlCurve.length === 0) return null

    const maxAbsPnl = Math.max(
      Math.abs(maxProfit || 0),
      Math.abs(maxLoss || 0),
      Math.max(...pnlCurve.map((p) => Math.abs(p.pnl)), 1),
    )

    const points = pnlCurveToPoints(pnlCurve, pToY, maxAbsPnl, VIEW_WIDTH, ZERO_X)
    if (points.length < 2) return null

    const { profitPoints, lossPoints } = splitProfitLoss(points)
    const mainPath = buildSmoothPath(points)
    const profitFill = profitPoints.length >= 2 ? buildFillPath(profitPoints, ZERO_X) : ''
    const lossFill = lossPoints.length >= 2 ? buildFillPath(lossPoints, ZERO_X) : ''

    return { mainPath, profitFill, lossFill, points }
  }, [pnlCurve, minPrice, maxPrice, height, maxProfit, maxLoss])

  // Strike lines continue from candle chart
  const strikeLines = useMemo(() => {
    const lines: Array<{ y: number; color: string; dash: string; label: string | null }> = []
    if (!strikes) return lines
    const longPrices = [strikes.longPutStrike, strikes.longCallStrike]
      .filter((v): v is number => v != null && Number.isFinite(Number(v)))
      .map(Number)
    const shortPrices = [strikes.shortPutStrike, strikes.shortCallStrike]
      .filter((v): v is number => v != null && Number.isFinite(Number(v)))
      .map(Number)
    longPrices.forEach((p) => {
      if (p >= minPrice && p <= maxPrice) lines.push({ y: pToY(p), color: '#22c55e', dash: '5,4', label: `$${p}` })
    })
    shortPrices.forEach((p) => {
      if (p >= minPrice && p <= maxPrice) lines.push({ y: pToY(p), color: '#ef4444', dash: '5,4', label: null })
    })
    return lines
  }, [strikes, minPrice, maxPrice, height])

  const spotY = spotPrice != null ? pToY(spotPrice) : null

  const priceRange = maxPrice - minPrice
  const step = priceRange > 30 ? 5 : priceRange > 15 ? 2 : 1
  const startP = Math.ceil(minPrice / step) * step
  const priceTicks: Array<{ price: number; y: number }> = []
  for (let p = startP; p <= maxPrice; p += step) {
    priceTicks.push({ price: p, y: pToY(p) })
  }

  // Interpolate P&L at the current spot to render the "Now" badge
  const pnlAtSpotPoint: { pnl: number; pctOfRisk: number } | null = (() => {
    if (!pnlCurve || pnlCurve.length === 0 || spotPrice == null) return null
    let pnlAtSpot: number | null = null
    for (let i = 0; i < pnlCurve.length - 1; i++) {
      const a = pnlCurve[i]
      const b = pnlCurve[i + 1]
      if ((a.price <= spotPrice && b.price >= spotPrice) || (a.price >= spotPrice && b.price <= spotPrice)) {
        const t = (spotPrice - a.price) / ((b.price - a.price) || 1)
        pnlAtSpot = a.pnl + t * (b.pnl - a.pnl)
        break
      }
    }
    if (pnlAtSpot == null) return null
    const maxRisk = Math.abs(maxLoss || 1)
    const pctOfRisk = maxRisk > 0 ? (pnlAtSpot / maxRisk) * 100 : 0
    return { pnl: pnlAtSpot, pctOfRisk }
  })()

  return (
    <div className="w-[220px] min-w-[220px] bg-forge-bg border-l border-forge-border relative">
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${VIEW_WIDTH} ${height}`}
        preserveAspectRatio="none"
        style={{ display: 'block' }}
      >
        <defs>
          <linearGradient id="profitGrad" x1="1" y1="0" x2="0" y2="0">
            <stop offset="0%" stopColor="#22c55e" stopOpacity="0" />
            <stop offset="100%" stopColor="#22c55e" stopOpacity="0.5" />
          </linearGradient>
          <linearGradient id="lossGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#ef4444" stopOpacity="0" />
            <stop offset="100%" stopColor="#ef4444" stopOpacity="0.5" />
          </linearGradient>
        </defs>

        {/* Grid lines matching candle chart */}
        {priceTicks.map((t, i) => (
          <line key={i} x1={0} y1={t.y} x2={VIEW_WIDTH} y2={t.y} stroke="#1a1a2e" strokeWidth="0.5" />
        ))}

        {/* Zero line */}
        <line x1={ZERO_X} y1={topPad} x2={ZERO_X} y2={height - 28} stroke="#1a1a2e" strokeWidth="1" />

        {/* Strike lines continue (dimmer than candle panel) */}
        {strikeLines.map((sl, i) => (
          <line
            key={i}
            x1={0}
            y1={sl.y}
            x2={VIEW_WIDTH}
            y2={sl.y}
            stroke={sl.color}
            strokeWidth="1"
            strokeDasharray={sl.dash}
            opacity="0.4"
          />
        ))}

        {/* Payoff shape */}
        {paths && (
          <>
            {paths.profitFill && <path d={paths.profitFill} fill="url(#profitGrad)" />}
            {paths.lossFill && <path d={paths.lossFill} fill="url(#lossGrad)" />}
            <path d={paths.mainPath} fill="none" stroke="#22c55e" strokeWidth="2.5" />
          </>
        )}

        {/* Spot price horizontal line */}
        {spotY != null && spotPrice != null && (
          <>
            <line
              x1={0}
              y1={spotY}
              x2={VIEW_WIDTH}
              y2={spotY}
              stroke="#448aff"
              strokeWidth="1"
              strokeDasharray="3,3"
              opacity="0.5"
            />
            <rect
              x={VIEW_WIDTH - 48}
              y={spotY - 8}
              width={46}
              height={16}
              rx={3}
              fill="rgba(68, 138, 255, 0.13)"
              stroke="#448aff"
              strokeWidth="0.5"
            />
            <text
              x={VIEW_WIDTH - 25}
              y={spotY + 3}
              textAnchor="middle"
              fill="#448aff"
              fontSize="8"
              fontFamily="monospace"
            >
              ${spotPrice.toFixed(0)}
            </text>
          </>
        )}

        {/* Breakeven markers straddling the zero line */}
        {breakevens?.lower != null && (
          <g>
            <line
              x1={ZERO_X - 10}
              y1={pToY(breakevens.lower)}
              x2={ZERO_X + 10}
              y2={pToY(breakevens.lower)}
              stroke="#ffd600"
              strokeWidth="2"
            />
            <text
              x={ZERO_X - 14}
              y={pToY(breakevens.lower) + 3}
              textAnchor="end"
              fill="#ffd600"
              fontSize="8"
              fontFamily="monospace"
            >
              BE
            </text>
          </g>
        )}
        {breakevens?.upper != null && (
          <g>
            <line
              x1={ZERO_X - 10}
              y1={pToY(breakevens.upper)}
              x2={ZERO_X + 10}
              y2={pToY(breakevens.upper)}
              stroke="#ffd600"
              strokeWidth="2"
            />
            <text
              x={ZERO_X - 14}
              y={pToY(breakevens.upper) + 3}
              textAnchor="end"
              fill="#ffd600"
              fontSize="8"
              fontFamily="monospace"
            >
              BE
            </text>
          </g>
        )}

        {/* "Now: +$X (+X.X%)" badge at spot price, on LEFT of panel */}
        {paths && spotY != null && pnlAtSpotPoint != null && (() => {
          const { pnl, pctOfRisk } = pnlAtSpotPoint
          const isProfit = pnl > 0
          const nearBreakeven = Math.abs(pctOfRisk) < 10
          const badgeColor = nearBreakeven ? '#ffd600' : isProfit ? '#22c55e' : '#ef4444'
          const bgColor = nearBreakeven ? '#ffd60022' : isProfit ? '#22c55e22' : '#ef444422'
          const label = `Now: ${formatDollarPnl(pnl)} (${formatSignedPct(pctOfRisk)})`
          const badgeW = 140
          const badgeH = 18
          const rawX = 4
          let badgeY = spotY - badgeH / 2
          badgeY = Math.max(10, Math.min(badgeY, height - 28 - badgeH))
          return (
            <g>
              <rect x={rawX} y={badgeY} width={badgeW} height={badgeH} rx={3} fill={bgColor} stroke={badgeColor} strokeWidth="0.8" />
              <text
                x={rawX + badgeW / 2}
                y={badgeY + 12}
                textAnchor="middle"
                fill={badgeColor}
                fontSize="9"
                fontWeight="700"
                fontFamily="monospace"
              >
                {label}
              </text>
            </g>
          )
        })()}

        {/* No payoff data placeholder */}
        {!paths && (
          <text x={VIEW_WIDTH / 2} y={height / 2} textAnchor="middle" fill="#333" fontSize="11" fontFamily="monospace">
            No payoff data
          </text>
        )}

        {/* Strike labels on right edge */}
        {strikeLines.filter((sl) => sl.label).map((sl, i) => (
          <text
            key={`label-${i}`}
            x={VIEW_WIDTH - 4}
            y={sl.y + 3}
            textAnchor="end"
            fill={sl.color}
            fontSize="8"
            fontFamily="monospace"
            opacity="0.8"
          >
            {sl.label}
          </text>
        ))}
      </svg>
    </div>
  )
}

// Re-export types used by the parent container so imports stay tidy
export type { PnlPoint } from '@/lib/payoff-shape'
