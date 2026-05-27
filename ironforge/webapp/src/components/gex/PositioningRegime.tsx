'use client'
import type { Positioning } from '@/lib/gex/types'

const labelColor = (l: string) =>
  l === 'Bullish' ? 'text-green-400' : l === 'Bearish' ? 'text-red-400' : 'text-gray-300'

function pressureBand(score: number): string {
  if (score >= 67) return 'High conviction'
  if (score >= 34) return 'Moderate'
  return 'Low / balanced'
}

export default function PositioningRegime({ positioning }: { positioning?: Positioning }) {
  if (!positioning) {
    return (
      <div className="bg-forge-card border border-forge-border rounded-xl p-4">
        <h3 className="text-sm font-semibold text-white mb-2">Positioning Regime</h3>
        <p className="text-xs text-gray-500">Not available (after-hours fallback).</p>
      </div>
    )
  }
  const pct = Math.max(0, Math.min(100, positioning.pressure_score))
  return (
    <div className="bg-forge-card border border-forge-border rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-2">Positioning Regime</h3>
      <div className="flex items-baseline gap-3">
        <span className={`text-xl font-bold ${labelColor(positioning.regime_label)}`}>
          {positioning.regime_label}
        </span>
        <span className="text-sm text-gray-400">pressure {positioning.pressure_score}/100</span>
        <span className="text-xs text-amber-300">({pressureBand(positioning.pressure_score)})</span>
      </div>

      {/* Pressure bar with scale ticks */}
      <div className="mt-3 relative h-2 rounded-full bg-gray-800 overflow-hidden">
        <div className="h-full bg-amber-400" style={{ width: `${pct}%` }} />
        <div className="absolute top-0 h-full w-px bg-gray-600" style={{ left: '34%' }} />
        <div className="absolute top-0 h-full w-px bg-gray-600" style={{ left: '67%' }} />
      </div>
      <div className="flex justify-between text-[10px] text-gray-500 mt-1">
        <span>0 · balanced</span>
        <span>50</span>
        <span>100 · one-sided</span>
      </div>

      <p className="text-xs text-gray-400 mt-3">
        Call vs Put Pressure <span className="text-gray-200 font-mono">{positioning.call_vs_put_pressure.toFixed(3)}</span>
        <span className="text-gray-500"> (−1 = all puts, +1 = all calls)</span>
      </p>
      <p className="text-[11px] text-gray-500 mt-2 leading-relaxed">
        <span className="text-gray-400">Regime</span> = net directional lean (Bullish / Neutral / Bearish).{' '}
        <span className="text-gray-400">Pressure 0–100</span> = how lopsided positioning is — a blend of call-vs-put
        flow, net GEX size, and skew. Low = balanced / rangebound; high = strong one-sided conviction. (Our composite,
        not a TradingVolatility-exact figure.)
      </p>
    </div>
  )
}
