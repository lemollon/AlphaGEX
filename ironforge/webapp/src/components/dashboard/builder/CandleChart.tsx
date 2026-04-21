'use client'

/**
 * CandleChart — ported verbatim from
 * spreadworks/frontend/src/components/CandleChart.jsx.
 *
 * Pure SVG. Renders SPY intraday OHLCV + volume + strike overlay lines.
 * CRITICAL: minPrice/maxPrice come from the PARENT (ChartArea). This is
 * how strike horizontal lines align perfectly across the divider to the
 * sideways PayoffPanel on the right — they share the same priceToY scale.
 *
 * The 80px right margin (CHART_RIGHT_MARGIN) is intentionally protected:
 * no candle, wick, volume bar, or date label enters it. Only the current-
 * price dashed vertical line and the $XXX.XX badge sit in that zone.
 */
import { useMemo } from 'react'
import { priceToY, type Candle } from '@/lib/price-scale'

export type { Candle } from '@/lib/price-scale'

interface CandleChartProps {
  candles: Candle[] | null | undefined
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
  fetchError?: string | null
  candleSpacing?: number
}

const CHART_LEFT_MARGIN = 50
const CHART_RIGHT_MARGIN = 80
const DEFAULT_CANDLE_SPACING = 9
const TOP_PAD = 10
const BOTTOM_PAD = 28

export default function CandleChart({
  candles,
  minPrice,
  maxPrice,
  height,
  strikes,
  spotPrice,
  fetchError,
  candleSpacing = DEFAULT_CANDLE_SPACING,
}: CandleChartProps) {
  const barWidth = Math.max(2, Math.round(candleSpacing * 0.67))

  const chartData = useMemo(() => {
    if (!candles || candles.length === 0) return null
    const svgWidth = 900
    const availableWidth = svgWidth - CHART_LEFT_MARGIN - CHART_RIGHT_MARGIN
    const maxCandles = Math.floor(availableWidth / candleSpacing)
    const visibleCandles = candles.slice(-maxCandles)

    const plotH = height - TOP_PAD - BOTTOM_PAD
    const maxVol = Math.max(...visibleCandles.map((c) => c.volume || 0), 1)
    const pToY = (p: number) => TOP_PAD + priceToY(p, minPrice, maxPrice, plotH)
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

    const dateLabels: Array<{ x: number; label: string }> = []
    const labelEvery = Math.max(10, Math.round(20 * DEFAULT_CANDLE_SPACING / candleSpacing))
    for (let i = 0; i < visibleCandles.length; i += labelEvery) {
      const c = visibleCandles[i]
      const labelX = CHART_LEFT_MARGIN + i * candleSpacing
      if (c && c.time && labelX < svgWidth - CHART_RIGHT_MARGIN) {
        const d = new Date(c.time)
        // Ported as intraday time-of-day (CT) rather than SpreadWorks' month/day
        // because SPARK is 1DTE — all candles are same-day.
        const label = d.toLocaleTimeString('en-US', {
          hour: 'numeric', minute: '2-digit', timeZone: 'America/Chicago',
        })
        dateLabels.push({ x: labelX, label })
      }
    }

    const priceTicks: Array<{ price: number; y: number }> = []
    const range = maxPrice - minPrice
    const step = range > 30 ? 5 : range > 15 ? 2 : 1
    const startP = Math.ceil(minPrice / step) * step
    for (let p = startP; p <= maxPrice; p += step) {
      priceTicks.push({ price: p, y: pToY(p) })
    }

    return { bars, svgWidth, plotH, pToY, dateLabels, priceTicks, lastCandleX }
  }, [candles, minPrice, maxPrice, height, candleSpacing, barWidth])

  if (!chartData) {
    return (
      <div className="flex-[3] flex flex-col items-center justify-center font-mono text-sm bg-forge-bg gap-3 px-6" style={{ height }}>
        {fetchError ? (
          <>
            <span className="text-red-400 font-semibold">Cannot load chart data</span>
            <span className="text-xs text-forge-muted text-center max-w-[400px] leading-relaxed">{fetchError}</span>
          </>
        ) : (
          <span className="text-forge-muted">No candle data available</span>
        )}
      </div>
    )
  }

  const { bars, svgWidth, pToY, dateLabels, priceTicks, lastCandleX } = chartData

  // Strike overlay lines — ported verbatim
  const strikeLines: Array<{ y: number; color: string; dash: string; label: string }> = []
  if (strikes) {
    const longPrices = [strikes.longPutStrike, strikes.longCallStrike].filter((v): v is number => v != null && Number.isFinite(Number(v))).map(Number)
    const shortPrices = [strikes.shortPutStrike, strikes.shortCallStrike].filter((v): v is number => v != null && Number.isFinite(Number(v))).map(Number)
    longPrices.forEach((p) => {
      if (p >= minPrice && p <= maxPrice) strikeLines.push({ y: pToY(p), color: '#22c55e', dash: '5,4', label: `$${p}` })
    })
    shortPrices.forEach((p) => {
      if (p >= minPrice && p <= maxPrice) strikeLines.push({ y: pToY(p), color: '#ef4444', dash: '5,4', label: `$${p}` })
    })
  }

  const spotY = spotPrice != null ? pToY(spotPrice) : null

  return (
    <div className="flex-[3] overflow-hidden bg-forge-bg">
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${svgWidth} ${height}`}
        preserveAspectRatio="none"
        style={{ display: 'block' }}
      >
        {/* Grid lines */}
        {priceTicks.map((t, i) => (
          <g key={i}>
            <line x1={CHART_LEFT_MARGIN} y1={t.y} x2={svgWidth} y2={t.y} stroke="#1a1a2e" strokeWidth="0.5" />
            <text x={CHART_LEFT_MARGIN - 6} y={t.y + 3} textAnchor="end" fill="#555" fontSize="9" fontFamily="monospace">
              ${t.price}
            </text>
          </g>
        ))}

        {/* Strike lines */}
        {strikeLines.map((sl, i) => (
          <g key={`strike-${i}`}>
            <line x1={CHART_LEFT_MARGIN} y1={sl.y} x2={svgWidth} y2={sl.y} stroke={sl.color} strokeWidth="1" strokeDasharray={sl.dash} opacity="0.7" />
            <text x={CHART_LEFT_MARGIN + 4} y={sl.y - 3} fill={sl.color} fontSize="10" fontWeight="600" fontFamily="monospace">
              {sl.label}
            </text>
          </g>
        ))}

        {/* Volume bars */}
        {bars.map((b, i) => (
          <rect key={`vol-${i}`} x={b.x} y={b.volY} width={barWidth} height={b.volH} fill={b.volColor} />
        ))}

        {/* Candlesticks */}
        {bars.map((b, i) => (
          <g key={`candle-${i}`}>
            <line x1={b.centerX} y1={b.wickTop} x2={b.centerX} y2={b.wickBottom} stroke={b.color} strokeWidth="1" />
            <rect x={b.x} y={b.bodyTop} width={barWidth} height={b.bodyHeight} fill={b.color} />
          </g>
        ))}

        {/* Current price line + badge in protected right margin */}
        {lastCandleX != null && spotY != null && spotPrice != null && (
          <>
            <line x1={lastCandleX} y1={TOP_PAD} x2={lastCandleX} y2={height - BOTTOM_PAD} stroke="#448aff" strokeWidth="1" strokeDasharray="3,3" opacity="0.6" />
            <rect x={svgWidth - CHART_RIGHT_MARGIN + 8} y={spotY - 8} width={60} height={16} rx={3} fill="#448aff" />
            <text x={svgWidth - CHART_RIGHT_MARGIN + 38} y={spotY + 3} textAnchor="middle" fill="#fff" fontSize="9" fontWeight="600" fontFamily="monospace">
              ${spotPrice.toFixed(2)}
            </text>
          </>
        )}

        {/* Date labels */}
        {dateLabels.map((dl, i) => (
          <text key={`date-${i}`} x={dl.x} y={height - 6} fill="#555" fontSize="9" fontFamily="monospace">
            {dl.label}
          </text>
        ))}
      </svg>
    </div>
  )
}
