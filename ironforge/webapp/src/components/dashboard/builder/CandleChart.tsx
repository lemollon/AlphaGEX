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
  /**
   * Named horizontal lines layered above strike lines. Used by BLAZE's
   * Directional Chart to overlay GEX context (call wall, put wall, flip,
   * ±1σ ribbon) — the existing `strikes` prop only handles IC long/short
   * legs with hardcoded green/red colors.
   */
  gexLines?: Array<{
    price: number
    color: string
    label: string
    /** SVG stroke-dasharray. Empty string = solid. Default '6,3'. */
    dash?: string
    /** 0-1, default 0.85 */
    opacity?: number
    /** Side to anchor the label. Default 'left'. */
    side?: 'left' | 'right'
  }>
  /**
   * Time-varying overlay polylines. Each series is drawn as a connected
   * line through (time, price) points, aligned to the candle x-axis via
   * timestamp interpolation. Used by BLAZE Phase 2 to show how the GEX
   * walls / flip moved through the day rather than a single static line.
   *
   * Points outside the candle time window are clipped. Series with < 2
   * in-range points render nothing.
   */
  gexTimeSeries?: Array<{
    label: string
    color: string
    dash?: string
    /** 0-1, default 0.9 */
    opacity?: number
    /** SVG stroke-width, default 1.5 */
    strokeWidth?: number
    points: Array<{ time: string; price: number }>
  }>
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
  gexLines,
  gexTimeSeries,
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
      const color = isUp ? '#34d399' : '#f87171'
      const bodyTop = pToY(Math.max(c.open, c.close))
      const bodyBottom = pToY(Math.min(c.open, c.close))
      const bodyHeight = Math.max(bodyBottom - bodyTop, 1)
      const wickTop = pToY(c.high)
      const wickBottom = pToY(c.low)
      const volH = ((c.volume || 0) / maxVol) * 40
      const volY = height - BOTTOM_PAD - volH
      return { x, centerX, bodyTop, bodyHeight, wickTop, wickBottom, color, volH, volY, volColor: isUp ? '#34d39944' : '#f8717144', time: c.time }
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

    // Time-to-x lookup for gexTimeSeries: returns the x coordinate of a
    // given ISO/Date timestamp interpolated between adjacent candles.
    // Returns null if the timestamp falls outside the rendered candle range.
    const candleTimes = visibleCandles.map((c) => {
      const t = new Date(c.time).getTime()
      return Number.isFinite(t) ? t : null
    })
    const timeToX = (iso: string): number | null => {
      const t = new Date(iso).getTime()
      if (!Number.isFinite(t)) return null
      // Before first candle → clip to first candle x
      const first = candleTimes[0]
      const last = candleTimes[candleTimes.length - 1]
      if (first == null || last == null) return null
      if (t <= first) return CHART_LEFT_MARGIN
      if (t >= last) return CHART_LEFT_MARGIN + (candleTimes.length - 1) * candleSpacing
      // Binary search for the candle index where candleTimes[i] <= t < candleTimes[i+1]
      let lo = 0, hi = candleTimes.length - 1
      while (lo < hi - 1) {
        const mid = (lo + hi) >> 1
        const m = candleTimes[mid]
        if (m == null) { lo = mid; continue }
        if (m <= t) lo = mid; else hi = mid
      }
      const tLo = candleTimes[lo]
      const tHi = candleTimes[hi]
      if (tLo == null || tHi == null || tHi === tLo) return CHART_LEFT_MARGIN + lo * candleSpacing
      const frac = (t - tLo) / (tHi - tLo)
      return CHART_LEFT_MARGIN + (lo + frac) * candleSpacing
    }

    return { bars, svgWidth, plotH, pToY, dateLabels, priceTicks, lastCandleX, timeToX }
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

  const { bars, svgWidth, pToY, dateLabels, priceTicks, lastCandleX, timeToX } = chartData

  // Compose polyline points for each gexTimeSeries entry. Points outside
  // the rendered candle window are clipped (timeToX returns null), and
  // their adjacent in-range neighbors stitch the line across the gap.
  const polylines: Array<{ pts: string; color: string; dash: string; opacity: number; strokeWidth: number; label: string; lastX: number; lastY: number; lastPrice: number }> = []
  if (gexTimeSeries && gexTimeSeries.length > 0) {
    for (const series of gexTimeSeries) {
      const coords: Array<{ x: number; y: number; price: number }> = []
      for (const p of series.points) {
        if (!Number.isFinite(p.price)) continue
        if (p.price < minPrice || p.price > maxPrice) continue
        const x = timeToX(p.time)
        if (x == null) continue
        coords.push({ x, y: pToY(p.price), price: p.price })
      }
      if (coords.length < 2) continue
      const pts = coords.map(c => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ')
      const tail = coords[coords.length - 1]
      polylines.push({
        pts,
        color: series.color,
        dash: series.dash ?? '0',
        opacity: series.opacity ?? 0.9,
        strokeWidth: series.strokeWidth ?? 1.5,
        label: series.label,
        lastX: tail.x,
        lastY: tail.y,
        lastPrice: tail.price,
      })
    }
  }

  // Strike overlay lines — ported verbatim
  const strikeLines: Array<{ y: number; color: string; dash: string; label: string }> = []
  if (strikes) {
    const longPrices = [strikes.longPutStrike, strikes.longCallStrike].filter((v): v is number => v != null && Number.isFinite(Number(v))).map(Number)
    const shortPrices = [strikes.shortPutStrike, strikes.shortCallStrike].filter((v): v is number => v != null && Number.isFinite(Number(v))).map(Number)
    longPrices.forEach((p) => {
      if (p >= minPrice && p <= maxPrice) strikeLines.push({ y: pToY(p), color: '#34d399', dash: '5,4', label: `$${p}` })
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

        {/* GEX time-series polylines (BLAZE Phase 2). Drawn below strike
            lines and gexLines so the static "now" line + IC strikes win the
            z-order if they coincide with the polyline tail. */}
        {polylines.map((p, i) => (
          <g key={`gex-series-${i}`}>
            <polyline
              points={p.pts}
              fill="none"
              stroke={p.color}
              strokeWidth={p.strokeWidth}
              strokeDasharray={p.dash}
              opacity={p.opacity}
            />
            {/* Right-edge "now" marker — small dot + label at the tail */}
            <circle cx={p.lastX} cy={p.lastY} r={2.5} fill={p.color} opacity={Math.max(0.9, p.opacity)} />
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

        {/* GEX overlay lines (BLAZE Directional Chart) — call wall, put wall,
            flip point, ±1σ ribbon. Drawn above strike lines so they win the
            z-order if a strike happens to coincide with a wall. */}
        {gexLines?.map((g, i) => {
          if (!Number.isFinite(g.price) || g.price < minPrice || g.price > maxPrice) return null
          const y = pToY(g.price)
          const opacity = g.opacity ?? 0.85
          const dash = g.dash ?? '6,3'
          const side = g.side ?? 'left'
          return (
            <g key={`gex-${i}`}>
              <line
                x1={CHART_LEFT_MARGIN}
                y1={y}
                x2={svgWidth - CHART_RIGHT_MARGIN}
                y2={y}
                stroke={g.color}
                strokeWidth="1.5"
                strokeDasharray={dash}
                opacity={opacity}
              />
              {side === 'left' ? (
                <rect x={CHART_LEFT_MARGIN + 4} y={y - 13} rx={2} ry={2}
                  width={g.label.length * 6 + 8} height={12} fill={g.color} opacity="0.18" />
              ) : null}
              <text
                x={side === 'right' ? svgWidth - CHART_RIGHT_MARGIN - 6 : CHART_LEFT_MARGIN + 8}
                y={y - 4}
                fill={g.color}
                fontSize="10"
                fontWeight="700"
                fontFamily="monospace"
                textAnchor={side === 'right' ? 'end' : 'start'}
              >
                {g.label}
              </text>
            </g>
          )
        })}

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
            <line x1={lastCandleX} y1={TOP_PAD} x2={lastCandleX} y2={height - BOTTOM_PAD} stroke="#3b82f6" strokeWidth="1" strokeDasharray="3,3" opacity="0.6" />
            <rect x={svgWidth - CHART_RIGHT_MARGIN + 8} y={spotY - 8} width={60} height={16} rx={3} fill="#3b82f6" />
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
