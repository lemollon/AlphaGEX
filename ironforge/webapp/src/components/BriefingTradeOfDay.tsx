import type { TradeOfDay } from '@/lib/forgeBriefings/types'

export default function BriefingTradeOfDay({ trade }: { trade: TradeOfDay | null }) {
  if (!trade) return null
  const { strikes, payoff_points, pnl, contracts, entry_credit, exit_cost } = trade
  if (!payoff_points || payoff_points.length < 2) return null

  const w = 320, h = 140, padX = 20, padY = 16
  const xs = payoff_points.map(p => p.spot)
  const ys = payoff_points.map(p => p.pnl)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const xRange = maxX - minX || 1
  const yRange = (maxY - minY) || 1
  const xToPx = (x: number) => padX + ((x - minX) / xRange) * (w - 2 * padX)
  const yToPx = (y: number) => h - padY - ((y - minY) / yRange) * (h - 2 * padY)
  const path = payoff_points.map((p, i) => `${i === 0 ? 'M' : 'L'}${xToPx(p.spot).toFixed(1)},${yToPx(p.pnl).toFixed(1)}`).join(' ')
  const zeroY = yToPx(0)

  return (
    <div className="bg-forge-card rounded-lg p-4">
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="text-amber-300 text-sm uppercase tracking-wider">Trade of the Day</h3>
        <span className={pnl >= 0 ? 'text-emerald-400 font-medium' : 'text-red-400 font-medium'}>
          {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
        </span>
      </div>
      <div className="text-xs text-gray-400 mb-3">
        {contracts}× {strikes.ps}/{strikes.pl}p{strikes.cs ? ` · ${strikes.cs}/${strikes.cl}c` : ''} · in {entry_credit.toFixed(2)} → out {exit_cost.toFixed(2)}
      </div>
      <svg width="100%" viewBox={`0 0 ${w} ${h}`} className="overflow-visible">
        <line x1={padX} y1={zeroY} x2={w - padX} y2={zeroY} stroke="#374151" strokeDasharray="3,3" />
        <path d={path} fill="none" stroke="#fbbf24" strokeWidth={1.5} />
      </svg>
    </div>
  )
}
