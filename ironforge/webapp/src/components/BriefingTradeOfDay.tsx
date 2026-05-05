import type { TradeOfDay, MacroRibbon } from '@/lib/forgeBriefings/types'

/**
 * Payoff diagram for the day's headline IC trade.
 *  - Y-axis: P&L with min/max/zero labels and a dashed zero baseline.
 *  - X-axis: spot price endpoints, strike markers (faint vertical guides
 *    at PS/PL/CS/CL), and a brighter "spot at close" line with $ label.
 *  - Curve: amber line with a green/red gradient fill underneath, split
 *    at the zero baseline so the in-profit zone reads green and the
 *    in-loss tails read red.
 *  - Breakeven crossings (where the curve hits zero) get tiny markers
 *    so the trader can see the no-loss range at a glance.
 */
interface Props {
  trade: TradeOfDay | null
  macro?: MacroRibbon | null
}

const PAD_L = 44
const PAD_R = 18
const PAD_T = 22
const PAD_B = 38
const W = 480
const H = 220

function fmtMoney(n: number): string {
  const sign = n >= 0 ? '+' : '−'
  const abs = Math.abs(n)
  if (abs >= 1000) return `${sign}$${(abs / 1000).toFixed(1)}k`
  if (abs >= 100)  return `${sign}$${abs.toFixed(0)}`
  return `${sign}$${abs.toFixed(2)}`
}

function fmtSpot(n: number): string {
  return `$${n.toFixed(2)}`
}

/** Linear interpolation: where between (x0,y0)→(x1,y1) does y=0? */
function zeroCrossingX(x0: number, y0: number, x1: number, y1: number): number {
  if (y0 === y1) return x0
  return x0 + (x1 - x0) * (-y0 / (y1 - y0))
}

export default function BriefingTradeOfDay({ trade, macro }: Props) {
  if (!trade) return null
  const { strikes, payoff_points, pnl, contracts, entry_credit, exit_cost } = trade
  if (!payoff_points || payoff_points.length < 2) return null

  const xs = payoff_points.map(p => p.spot)
  const ys = payoff_points.map(p => p.pnl)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  let minY = Math.min(0, ...ys), maxY = Math.max(0, ...ys)
  if (minY === maxY) { minY -= 1; maxY += 1 }
  const yPad = (maxY - minY) * 0.08
  minY -= yPad
  maxY += yPad
  const xRange = maxX - minX || 1
  const yRange = maxY - minY

  const innerW = W - PAD_L - PAD_R
  const innerH = H - PAD_T - PAD_B
  const xToPx = (x: number) => PAD_L + ((x - minX) / xRange) * innerW
  const yToPx = (y: number) => PAD_T + (1 - (y - minY) / yRange) * innerH
  const zeroPx = yToPx(0)

  // Sample a denser path along payoff_points (already smooth, so just polyline).
  const linePath = payoff_points.map((p, i) => {
    const cmd = i === 0 ? 'M' : 'L'
    return `${cmd}${xToPx(p.spot).toFixed(1)},${yToPx(p.pnl).toFixed(1)}`
  }).join(' ')

  // Profit area: closed polygon along the line, clipped to zero baseline
  // for the upper region. Loss area mirrors below.
  const profitClip: string[] = []
  const lossClip: string[]   = []
  for (let i = 0; i < payoff_points.length; i++) {
    const p = payoff_points[i]
    const xpx = xToPx(p.spot)
    const ypx = yToPx(p.pnl)
    if (p.pnl >= 0) {
      profitClip.push(`${i === 0 || profitClip.length === 0 ? 'M' : 'L'}${xpx.toFixed(1)},${ypx.toFixed(1)}`)
    } else {
      lossClip.push(`${i === 0 || lossClip.length === 0 ? 'M' : 'L'}${xpx.toFixed(1)},${ypx.toFixed(1)}`)
    }
  }
  // Close each clip down to the zero baseline.
  const closeProfit = profitClip.length ? profitClip.join(' ') + ` L${xToPx(maxX).toFixed(1)},${zeroPx.toFixed(1)} L${xToPx(minX).toFixed(1)},${zeroPx.toFixed(1)} Z` : ''
  const closeLoss   = lossClip.length   ? lossClip.join(' ')   + ` L${xToPx(maxX).toFixed(1)},${zeroPx.toFixed(1)} L${xToPx(minX).toFixed(1)},${zeroPx.toFixed(1)} Z` : ''

  // Breakeven crossings.
  const breakevens: number[] = []
  for (let i = 1; i < payoff_points.length; i++) {
    const a = payoff_points[i - 1]
    const b = payoff_points[i]
    if ((a.pnl < 0 && b.pnl >= 0) || (a.pnl > 0 && b.pnl <= 0)) {
      breakevens.push(zeroCrossingX(a.spot, a.pnl, b.spot, b.pnl))
    }
  }

  // Strike markers — only render those inside the chart x-range.
  const strikeMarkers: Array<{ x: number; label: string }> = []
  if (strikes.pl >= minX && strikes.pl <= maxX) strikeMarkers.push({ x: strikes.pl, label: `${strikes.pl}PL` })
  if (strikes.ps >= minX && strikes.ps <= maxX) strikeMarkers.push({ x: strikes.ps, label: `${strikes.ps}PS` })
  if (strikes.cs && strikes.cs >= minX && strikes.cs <= maxX) strikeMarkers.push({ x: strikes.cs, label: `${strikes.cs}CS` })
  if (strikes.cl && strikes.cl >= minX && strikes.cl <= maxX) strikeMarkers.push({ x: strikes.cl, label: `${strikes.cl}CL` })

  const spot = macro?.spy_close
  const showSpot = typeof spot === 'number' && spot >= minX && spot <= maxX

  // Max profit / max loss values from the curve.
  const curveMaxPnl = Math.max(...ys)
  const curveMinPnl = Math.min(...ys)

  return (
    <div className="bg-forge-card rounded-lg p-4">
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="text-amber-300 text-sm uppercase tracking-wider">Trade of the Day</h3>
        <span className={pnl >= 0 ? 'text-emerald-400 font-medium' : 'text-red-400 font-medium'}>
          {fmtMoney(pnl)}
        </span>
      </div>
      <div className="text-xs text-gray-400 mb-3">
        {contracts}× {strikes.ps}/{strikes.pl}p{strikes.cs ? ` · ${strikes.cs}/${strikes.cl}c` : ''} · in {entry_credit.toFixed(2)} → out {exit_cost.toFixed(2)}
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }} className="overflow-visible">
        <defs>
          <linearGradient id="payoffProfit" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"  stopColor="#34d399" stopOpacity={0.30} />
            <stop offset="100%" stopColor="#34d399" stopOpacity={0.0} />
          </linearGradient>
          <linearGradient id="payoffLoss" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"  stopColor="#f87171" stopOpacity={0.0} />
            <stop offset="100%" stopColor="#f87171" stopOpacity={0.30} />
          </linearGradient>
        </defs>

        {/* Strike vertical guides — drawn behind everything */}
        {strikeMarkers.map((s, i) => {
          const x = xToPx(s.x)
          return (
            <g key={i}>
              <line x1={x} y1={PAD_T} x2={x} y2={PAD_T + innerH} stroke="#1f2937" strokeWidth={1} />
              <text x={x} y={H - 22} textAnchor="middle" fontSize={9} fill="#6b7280">{s.label}</text>
            </g>
          )
        })}

        {/* Profit + loss area fills (rendered before line + baseline) */}
        {closeProfit ? <path d={closeProfit} fill="url(#payoffProfit)" /> : null}
        {closeLoss   ? <path d={closeLoss}   fill="url(#payoffLoss)"   /> : null}

        {/* Zero baseline */}
        <line x1={PAD_L} y1={zeroPx} x2={PAD_L + innerW} y2={zeroPx}
          stroke="#4b5563" strokeDasharray="3,3" strokeWidth={1} />

        {/* Y-axis labels: max, 0, min */}
        <text x={PAD_L - 6} y={PAD_T + 4} textAnchor="end" fontSize={10} fill="#9ca3af">{fmtMoney(maxY)}</text>
        <text x={PAD_L - 6} y={zeroPx + 3} textAnchor="end" fontSize={10} fill="#6b7280">0</text>
        <text x={PAD_L - 6} y={PAD_T + innerH + 2} textAnchor="end" fontSize={10} fill="#9ca3af">{fmtMoney(minY)}</text>

        {/* Payoff curve */}
        <path d={linePath} fill="none" stroke="#fbbf24" strokeWidth={1.75}
          strokeLinejoin="round" strokeLinecap="round" />

        {/* Breakeven dots + tick under axis */}
        {breakevens.map((bx, i) => {
          const x = xToPx(bx)
          return (
            <g key={i}>
              <circle cx={x} cy={zeroPx} r={3} fill="#fbbf24" stroke="#0b0b0d" strokeWidth={1.25} />
              <line x1={x} y1={PAD_T + innerH} x2={x} y2={PAD_T + innerH + 4} stroke="#fbbf24" strokeWidth={1} />
              <text x={x} y={PAD_T + innerH + 14} textAnchor="middle" fontSize={9} fill="#fbbf24">{fmtSpot(bx)}</text>
            </g>
          )
        })}

        {/* Spot-at-close marker */}
        {showSpot && spot !== undefined ? (() => {
          const sx = xToPx(spot)
          return (
            <g>
              <line x1={sx} y1={PAD_T - 6} x2={sx} y2={PAD_T + innerH} stroke="#e5e7eb" strokeWidth={1.25} strokeDasharray="2,3" />
              <rect x={sx - 30} y={PAD_T - 16} rx={3} ry={3} width={60} height={14} fill="#e5e7eb" fillOpacity={0.12} stroke="#e5e7eb" strokeWidth={0.75} />
              <text x={sx} y={PAD_T - 6} textAnchor="middle" fontSize={10} fontWeight={600} fill="#e5e7eb">SPY {fmtSpot(spot)}</text>
            </g>
          )
        })() : null}

        {/* X-axis spot endpoints */}
        <text x={PAD_L} y={H - 6} textAnchor="start" fontSize={10} fill="#6b7280">{fmtSpot(minX)}</text>
        <text x={PAD_L + innerW} y={H - 6} textAnchor="end" fontSize={10} fill="#6b7280">{fmtSpot(maxX)}</text>
      </svg>

      {/* Caption row: max profit / max loss summary */}
      <div className="mt-2 flex items-center justify-between text-[11px] text-gray-500">
        <span>Max profit on chart: <span className="text-emerald-400">{fmtMoney(curveMaxPnl)}</span></span>
        <span>Max loss on chart: <span className="text-red-400">{fmtMoney(curveMinPnl)}</span></span>
      </div>
    </div>
  )
}
