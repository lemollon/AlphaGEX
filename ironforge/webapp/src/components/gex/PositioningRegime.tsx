'use client'
import type { Positioning } from '@/lib/gex/types'

const labelColor = (l: string) =>
  l === 'Bullish' ? 'text-green-400' : l === 'Bearish' ? 'text-red-400' : 'text-gray-300'

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
      </div>
      <div className="mt-2 h-2 rounded-full bg-gray-800 overflow-hidden">
        <div className="h-full bg-amber-400" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-xs text-gray-500 mt-2">Call vs Put Pressure {positioning.call_vs_put_pressure.toFixed(3)}</p>
    </div>
  )
}
