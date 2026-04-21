'use client'

/**
 * CandleChart — ported from spreadworks/frontend/src/components/CandleChart.jsx.
 * Pure SVG. Renders SPY intraday OHLCV with horizontal strike lines for the
 * current IC overlay. GEX lines are intentionally omitted here (IronForge
 * has no GEX endpoint; adding one is a separate commit per scope discipline).
 *
 * Data:
 *   candles  — from /api/{bot}/builder/candles
 *   strikes  — from /api/{bot}/builder/snapshot (position.put_long_strike, etc.)
 *   spotPrice — latest SPY quote
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

interface CandleChartProps {
  candles: Candle[] | null | undefined
  spotPrice?: number | null
  strikes?: {
    putLong?: number | null
    putShort?: number | null
    callShort?: number | null
    callLong?: number | null
  } | null
  height?: number
  candleSpacing?: number
}

const CHART_LEFT_MARGIN = 50
const CHART_RIGHT_MARGIN = 90
const DEFAULT_CANDLE_SPACING = 8
const TOP_PAD = 10
const BOTTOM_PAD = 28

function priceToY(price: number, minPrice: number, maxPrice: number, plotH: number): number {
  if (maxPrice === minPrice) return plotH / 2
  return plotH - ((price - minPrice) / (maxPrice - minPrice)) * plotH
}

export default function CandleChart({
  candles,
  spotPrice,
  strikes,
  height = 300,
  candleSpacing = DEFAULT_CANDLE_SPACING,
}: CandleChartProps) {
  const barWidth = Math.max(2, Math.round(candleSpacing * 0.67))

  const chartData = useMemo(() => {
    if (!candles || candles.length === 0) return null
    const svgWidth = 900
    const availableWidth = svgWidth - CHART_LEFT_MARGIN - CHART_RIGHT_MARGIN
    const maxCandles = Math.floor(availableWidth / candleSpacing)
    const visibleCandles = candles.slice(-maxCandles)

    // Price range: expand to include strikes if any are nearby
    let minP = Math.min(...visibleCandles.map((c) => c.low))
    let maxP = Math.max(...visibleCandles.map((c) => c.high))
    if (strikes) {
      const strikeVals = [strikes.putLong, strikes.putShort, strikes.callShort, strikes.callLong]
        .filter((v): v is number => v != null && Number.isFinite(v))
      if (strikeVals.length) {
        minP = Math.min(minP, ...strikeVals)
        maxP = Math.max(maxP, ...strikeVals)
      }
    }
    // Add a small padding so strikes don't sit flush against the edges
    const pad = Math.max((maxP - minP) * 0.05, 0.5)
    minP -= pad
    maxP += pad

    const plotH = height - TOP_PAD - BOTTOM_PAD
    const maxVol = Math.max(...visibleCandles.map((c) => c.volume || 0), 1)
    const pToY = (p: number) => TOP_PAD + priceToY(p, minP, maxP, plotH)
    const lastCandleX = CHART_LEFT_MARGIN + (visibleCandles.length - 1) * candleSpacing

    const bars = visibleCandles.map((c, i) => {
      const x = CHART_LEFT_MARGIN + i * candleSpacing - barWidth / 2
      const centerX = CHART_LEFT_MARGIN + i * candleSpacing
      const isUp = c.close >= c.open
      const color = isUp ? '#26a69a' : '#ef5350'
      const bodyTop = pToY(Math.max(c.open, c.close))
      const bodyBottom = pToY(Math.min(c.open, c.close))
      const bodyHeight = Math.max(bodyBottom - bodyTop, 1)
      const wickTop = pToY(c.high)
      const wickBottom = pToY(c.low)
      const volH = ((c.volume || 0) / maxVol) * 40
      const volY = height - BOTTOM_PAD - volH
      return { x, centerX, bodyTop, bodyHeight, wickTop, wickBottom, color, volH, volY, volColor: isUp ? '#26a69a44' : '#ef535044', time: c.time }
    })

    // Time labels every N candles, skipping the right-margin protected zone
    const timeLabels: Array<{ x: number; label: string }> = []
    const labelEvery = Math.max(8, Math.round(16 * DEFAULT_CANDLE_SPACING / candleSpacing))
    for (let i = 0; i < visibleCandles.length; i += labelEvery) {
      const c = visibleCandles[i]
      const labelX = CHART_LEFT_MARGIN + i * candleSpacing
      if (c && c.time && labelX < svgWidth - CHART_RIGHT_MARGIN) {
        const d = new Date(c.time)
        const label = d.toLocaleTimeString('en-US', {
          hour: 'numeric', minute: '2-digit', timeZone: 'America/Chicago',
        })
        timeLabels.push({ x: labelX, label })
      }
    }

    // Price grid ticks
    const priceTicks: Array<{ price: number; y: number }> = []
    const range = maxP - minP
    const step = range > 30 ? 5 : range > 15 ? 2 : range > 5 ? 1 : 0.5
    const startP = Math.ceil(minP / step) * step
    for (let p = startP; p <= maxP; p += step) {
      priceTicks.push({ price: p, y: pToY(p) })
    }

    return { svgWidth, bars, pToY, timeLabels, priceTicks, lastCandleX, minP, maxP, plotH }
  }, [candles, strikes, height, candleSpacing, barWidth])

  if (!chartData) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-6 text-center" style={{ height }}>
        <p className="text-forge-muted text-sm mt-8">No candle data yet — load during market hours.</p>
      </div>
    )
  }

  const { svgWidth, bars, pToY, timeLabels, priceTicks, lastCandleX, minP, maxP } = chartData

  // Strike overlay lines
  const strikeLines: Array<{ y: number; color: string; label: string }> = []
  if (strikes) {
    const longs = [strikes.putLong, strikes.callLong].filter((v): v is number => v != null)
    const shorts = [strikes.putShort, strikes.callShort].filter((v): v is number => v != null)
    longs.forEach((p) => {
      if (p >= minP && p <= maxP) strikeLines.push({ y: pToY(p), color: '#22c55e', label: `$${p.toFixed(0)}` })
    })
    shorts.forEach((p) => {
      if (p >= minP && p <= maxP) strikeLines.push({ y: pToY(p), color: '#ef4444', label: `$${p.toFixed(0)}` })
    })
  }

  const spotY = spotPrice != null ? pToY(spotPrice) : null

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 overflow-hidden">
      <svg width="100%" height={height} viewBox={`0 0 ${svgWidth} ${height}`} preserveAspectRatio="none" style={{ display: 'block' }}>
        {/* Price grid */}
        {priceTicks.map((t, i) => (
          <g key={`pt-${i}`}>
            <line x1={CHART_LEFT_MARGIN} y1={t.y} x2={svgWidth} y2={t.y} stroke="#1a1a2e" strokeWidth="0.5" />
            <text x={CHART_LEFT_MARGIN - 6} y={t.y + 3} textAnchor="end" fill="#555" fontSize="9" fontFamily="monospace">
              ${t.price}
            </text>
          </g>
        ))}

        {/* Strike lines */}
        {strikeLines.map((sl, i) => (
          <g key={`sl-${i}`}>
            <line x1={CHART_LEFT_MARGIN} y1={sl.y} x2={svgWidth} y2={sl.y} stroke={sl.color} strokeWidth="1" strokeDasharray="5,4" opacity="0.7" />
            <text x={CHART_LEFT_MARGIN + 4} y={sl.y - 3} fill={sl.color} fontSize="10" fontWeight="600" fontFamily="monospace">
              {sl.label}
            </text>
          </g>
        ))}

        {/* Volume bars */}
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

        {/* Current price marker */}
        {lastCandleX != null && spotY != null && spotPrice != null && (
          <>
            <line x1={lastCandleX} y1={TOP_PAD} x2={lastCandleX} y2={height - BOTTOM_PAD} stroke="#448aff" strokeWidth="1" strokeDasharray="3,3" opacity="0.6" />
            <rect x={svgWidth - CHART_RIGHT_MARGIN + 8} y={spotY - 9} width={72} height={18} rx={3} fill="#448aff" />
            <text x={svgWidth - CHART_RIGHT_MARGIN + 44} y={spotY + 4} textAnchor="middle" fill="#fff" fontSize="10" fontWeight="600" fontFamily="monospace">
              ${spotPrice.toFixed(2)}
            </text>
          </>
        )}

        {/* Time labels */}
        {timeLabels.map((tl, i) => (
          <text key={`tl-${i}`} x={tl.x} y={height - 6} fill="#555" fontSize="9" fontFamily="monospace">
            {tl.label}
          </text>
        ))}
      </svg>
    </div>
  )
}
