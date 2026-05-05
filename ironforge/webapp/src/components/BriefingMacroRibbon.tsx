import type { MacroRibbon } from '@/lib/forgeBriefings/types'

export default function BriefingMacroRibbon({ data }: { data: MacroRibbon | null }) {
  if (!data) return null
  const sign = (n: number) => (n >= 0 ? '+' : '') + n.toFixed(2)
  return (
    <div className="rounded-lg border border-gray-800 bg-forge-card/50 px-4 py-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
      <div><span className="text-gray-500 text-xs">SPY</span> <span className="text-gray-200">{data.spy_close.toFixed(2)}</span> <span className="text-gray-400">range {data.spy_range_pct.toFixed(2)}%</span></div>
      <div className="text-gray-700">·</div>
      <div><span className="text-gray-500 text-xs">EM</span> <span className="text-gray-200">{data.em_pct.toFixed(2)}%</span></div>
      <div className="text-gray-700">·</div>
      <div><span className="text-gray-500 text-xs">VIX</span> <span className="text-gray-200">{data.vix.toFixed(2)}</span> <span className={data.vix_change >= 0 ? 'text-red-400' : 'text-emerald-400'}>{sign(data.vix_change)}</span></div>
      <div className="text-gray-700">·</div>
      <div><span className="text-gray-500 text-xs">Regime</span> <span className="text-gray-200">{data.regime}</span></div>
      <div className="text-gray-700">·</div>
      <div><span className="text-gray-500 text-xs">Pin Risk</span> <span className="text-gray-200">{data.pin_risk}</span></div>
    </div>
  )
}
