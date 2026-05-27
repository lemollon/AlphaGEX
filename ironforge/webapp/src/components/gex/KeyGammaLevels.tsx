'use client'
import type { GexAnalysisData, GexAllData } from '@/lib/gex/types'
import { topStrikesByGamma } from '@/lib/gex/derive'

// Adaptive magnitude formatter (matches HeaderMetrics/NetGexChart). Per-strike
// net-gamma scale varies, so never hard-code "M".
function gammaM(n: number): string {
  const a = Math.abs(n)
  if (a >= 1e9) return `${(n / 1e9).toFixed(1)}B`
  if (a >= 1e6) return `${(n / 1e6).toFixed(1)}M`
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}K`
  return n.toFixed(1)
}

function LevelRows({
  strikes, price, bandPct,
}: { strikes: { strike: number; net_gamma: number }[]; price: number; bandPct?: number }) {
  const { resistance, support } = topStrikesByGamma(strikes, price, 2, bandPct)
  return (
    <div className="space-y-1.5 text-sm">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 px-2 py-0.5 rounded bg-red-500/15 text-red-300 text-xs font-semibold shrink-0">Resist</span>
        <span className="text-gray-200">
          {resistance.length ? resistance.map((s) => `${s.strike} (${gammaM(s.net_gamma)})`).join(', ') : '—'}
        </span>
      </div>
      <div className="flex items-start gap-2">
        <span className="mt-0.5 px-2 py-0.5 rounded bg-green-500/15 text-green-300 text-xs font-semibold shrink-0">Support</span>
        <span className="text-gray-200">
          {support.length ? support.map((s) => `${s.strike} (${gammaM(s.net_gamma)})`).join(', ') : '—'}
        </span>
      </div>
    </div>
  )
}

export default function KeyGammaLevels({
  data, allData, allLoading,
}: { data: GexAnalysisData; allData?: GexAllData; allLoading?: boolean }) {
  const price = data.levels.price
  const allStrikes = allData?.gex_chart_all?.strikes || []
  const allPrice = allData?.spot_price || price
  return (
    <div className="bg-forge-card border border-forge-border rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-3">Key Gamma Levels</h3>

      <div className="text-[11px] uppercase tracking-wide text-amber-300 mb-1">
        0DTE ({data.expiration})
      </div>
      <LevelRows strikes={data.gex_chart.strikes} price={price} bandPct={0.05} />

      <div className="text-[11px] uppercase tracking-wide text-cyan-300 mt-4 mb-1">All Expirations</div>
      {allStrikes.length ? (
        <LevelRows strikes={allStrikes} price={allPrice} bandPct={0.15} />
      ) : (
        <p className="text-xs text-gray-500">{allLoading ? 'Loading full board…' : 'Not available.'}</p>
      )}

      <p className="text-[11px] text-gray-500 mt-3">Largest absolute-gamma strikes above (resist) / below (support) price.</p>
    </div>
  )
}
