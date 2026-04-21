'use client'

/**
 * PayoffDiagram — ported from spreadworks/frontend/src/components/PayoffDiagram.jsx.
 * Pure SVG. Renders the expiration P&L curve for the current IC:
 *   - green fill above zero (profit zone)
 *   - red fill below zero (loss zones)
 *   - blue stroke on the polyline
 *   - yellow dashed vertical at spot
 *   - purple vertical markers at each breakeven
 *   - grid + axis ticks
 *
 * Data comes from /api/{bot}/builder/snapshot .payoff (pnl_curve) and the
 * same response's metrics.breakeven_{low,high}. Keeps the SpreadWorks math
 * identical; only the styling maps to IronForge's forge-* Tailwind tokens.
 */
import { useMemo } from 'react'

interface PnlPoint {
  price: number
  pnl: number
}

interface PayoffDiagramProps {
  pnlCurve: PnlPoint[] | null | undefined
  spotPrice?: number | null
  breakevens?: { lower: number | null; upper: number | null } | null
  height?: number
  strikes?: {
    putLong?: number | null
    putShort?: number | null
    callShort?: number | null
    callLong?: number | null
  } | null
}

export default function PayoffDiagram({
  pnlCurve,
  spotPrice,
  breakevens,
  height = 280,
  strikes,
}: PayoffDiagramProps) {
  const svg = useMemo(() => {
    if (!pnlCurve || pnlCurve.length === 0) return null
    const W = 800
    const H = height
    const pad = { top: 20, right: 20, bottom: 30, left: 60 }
    const plotW = W - pad.left - pad.right
    const plotH = H - pad.top - pad.bottom

    const prices = pnlCurve.map((p) => p.price)
    const pnls = pnlCurve.map((p) => p.pnl)
    const minP = Math.min(...prices)
    const maxP = Math.max(...prices)
    const minPnl = Math.min(...pnls, 0)
    const maxPnl = Math.max(...pnls, 0)
    const priceRange = maxP - minP || 1
    const pnlRange = maxPnl - minPnl || 1

    const xScale = (p: number) => pad.left + ((p - minP) / priceRange) * plotW
    const yScale = (v: number) => pad.top + plotH - ((v - minPnl) / pnlRange) * plotH

    const points = pnlCurve.map((p) => `${xScale(p.price).toFixed(1)},${yScale(p.pnl).toFixed(1)}`)
    const linePath = `M${points.join('L')}`
    const zeroY = yScale(0)

    // Build polygon fills above/below zero by clipping the polyline to y=zeroY
    // at any crossings. This is a simplified approach that handles a 4-leg IC
    // curve where crossings happen near the breakevens only.
    const fillPoints: string[] = []
    const firstX = xScale(pnlCurve[0].price)
    const lastX = xScale(pnlCurve[pnlCurve.length - 1].price)
    for (const p of pnlCurve) {
      fillPoints.push(`${xScale(p.price).toFixed(1)},${yScale(p.pnl).toFixed(1)}`)
    }
    // Close polygon down to the zero line for clean fills
    const areaBelow = `${firstX.toFixed(1)},${zeroY.toFixed(1)} ${fillPoints.join(' ')} ${lastX.toFixed(1)},${zeroY.toFixed(1)}`

    const yTicks: Array<{ val: number; y: number }> = []
    const step = pnlRange / 4
    for (let i = 0; i <= 4; i++) {
      const val = minPnl + step * i
      yTicks.push({ val, y: yScale(val) })
    }
    const xTicks: Array<{ val: number; x: number }> = []
    const xStep = priceRange / 5
    for (let i = 0; i <= 5; i++) {
      const val = minP + xStep * i
      xTicks.push({ val, x: xScale(val) })
    }

    return { W, H, pad, plotW, plotH, linePath, areaBelow, zeroY, yTicks, xTicks, xScale, yScale }
  }, [pnlCurve, height])

  if (!svg) {
    return (
      <div className="rounded-xl border border-forge-border bg-forge-card/80 p-6 text-center">
        <p className="text-forge-muted text-sm">No payoff data — position may not be open.</p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-forge-border bg-forge-card/80 p-2">
      <svg viewBox={`0 0 ${svg.W} ${svg.H}`} style={{ width: '100%', maxHeight: height, display: 'block' }}>
        {/* Grid lines at y ticks */}
        {svg.yTicks.map((t, i) => (
          <line
            key={`yg-${i}`}
            x1={svg.pad.left}
            y1={t.y}
            x2={svg.pad.left + svg.plotW}
            y2={t.y}
            stroke="#1f2937"
            strokeWidth="0.5"
            strokeDasharray={t.val === 0 ? undefined : '2,3'}
          />
        ))}

        {/* Profit region — clip the filled polygon to above zero */}
        <defs>
          <clipPath id="profit-clip">
            <rect x={svg.pad.left} y={svg.pad.top} width={svg.plotW} height={svg.zeroY - svg.pad.top} />
          </clipPath>
          <clipPath id="loss-clip">
            <rect x={svg.pad.left} y={svg.zeroY} width={svg.plotW} height={svg.pad.top + svg.plotH - svg.zeroY} />
          </clipPath>
        </defs>
        <polygon points={svg.areaBelow} fill="rgba(34,197,94,0.16)" clipPath="url(#profit-clip)" />
        <polygon points={svg.areaBelow} fill="rgba(239,68,68,0.14)" clipPath="url(#loss-clip)" />

        {/* Zero line */}
        <line x1={svg.pad.left} y1={svg.zeroY} x2={svg.pad.left + svg.plotW} y2={svg.zeroY} stroke="#475569" strokeWidth="1" strokeDasharray="4,3" />

        {/* Strike vertical markers */}
        {strikes && (
          <>
            {(['putLong', 'putShort', 'callShort', 'callLong'] as const).map((role, i) => {
              const strike = strikes[role]
              if (strike == null) return null
              const x = svg.xScale(strike)
              if (x < svg.pad.left || x > svg.pad.left + svg.plotW) return null
              const isLong = role === 'putLong' || role === 'callLong'
              const color = isLong ? '#22c55e' : '#ef4444'
              return (
                <g key={`strike-${i}`}>
                  <line x1={x} y1={svg.pad.top} x2={x} y2={svg.pad.top + svg.plotH} stroke={color} strokeWidth="0.75" strokeDasharray="4,4" opacity="0.5" />
                  <text x={x} y={svg.pad.top + 10} textAnchor="middle" fill={color} fontSize="9" fontFamily="monospace" opacity="0.8">
                    ${strike.toFixed(0)}
                  </text>
                </g>
              )
            })}
          </>
        )}

        {/* P&L line */}
        <path d={svg.linePath} fill="none" stroke="#3b82f6" strokeWidth="2" />

        {/* Spot vertical line */}
        {spotPrice != null && (
          <g>
            <line x1={svg.xScale(spotPrice)} y1={svg.pad.top} x2={svg.xScale(spotPrice)} y2={svg.pad.top + svg.plotH} stroke="#facc15" strokeWidth="1" strokeDasharray="3,3" />
            <text x={svg.xScale(spotPrice)} y={svg.pad.top - 6} textAnchor="middle" fill="#facc15" fontSize="10" fontFamily="monospace">
              ${spotPrice.toFixed(2)}
            </text>
          </g>
        )}

        {/* Breakeven markers */}
        {breakevens && [breakevens.lower, breakevens.upper].filter((be): be is number => be != null).map((be, i) => (
          <g key={`be-${i}`}>
            <line x1={svg.xScale(be)} y1={svg.zeroY - 8} x2={svg.xScale(be)} y2={svg.zeroY + 8} stroke="#a78bfa" strokeWidth="2" />
            <text x={svg.xScale(be)} y={svg.zeroY + 20} textAnchor="middle" fill="#a78bfa" fontSize="9" fontFamily="monospace">
              BE ${be.toFixed(2)}
            </text>
          </g>
        ))}

        {/* Y axis */}
        {svg.yTicks.map((t, i) => (
          <g key={`yt-${i}`}>
            <line x1={svg.pad.left - 4} y1={t.y} x2={svg.pad.left} y2={t.y} stroke="#64748b" />
            <text x={svg.pad.left - 8} y={t.y + 3} textAnchor="end" fill="#64748b" fontSize="10" fontFamily="monospace">
              ${Math.round(t.val).toLocaleString()}
            </text>
          </g>
        ))}
        {/* X axis */}
        {svg.xTicks.map((t, i) => (
          <g key={`xt-${i}`}>
            <line x1={t.x} y1={svg.pad.top + svg.plotH} x2={t.x} y2={svg.pad.top + svg.plotH + 4} stroke="#64748b" />
            <text x={t.x} y={svg.pad.top + svg.plotH + 16} textAnchor="middle" fill="#64748b" fontSize="10" fontFamily="monospace">
              ${t.val.toFixed(0)}
            </text>
          </g>
        ))}
        {/* Border */}
        <rect x={svg.pad.left} y={svg.pad.top} width={svg.plotW} height={svg.plotH} fill="none" stroke="#334155" />
      </svg>
    </div>
  )
}
