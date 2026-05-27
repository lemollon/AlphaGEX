'use client'
import type { GexAnalysisData } from '@/lib/gex/types'

const ivStr = (v: number | null) => (v != null ? `${v}%` : 'N/A')

export default function SkewMeasures({ data }: { data: GexAnalysisData }) {
  const s = data.skew_measures
  const rows: { label: string; value: string }[] = [
    { label: 'Skew Ratio', value: s.skew_ratio != null ? s.skew_ratio.toFixed(3) : 'N/A' },
    { label: 'Call Skew', value: s.call_skew != null ? s.call_skew.toFixed(3) : 'N/A' },
    { label: 'ATM Call IV', value: ivStr(s.atm_call_iv) },
    { label: 'ATM Put IV', value: ivStr(s.atm_put_iv) },
    { label: 'OTM Call IV', value: ivStr(s.avg_otm_call_iv) },
    { label: 'OTM Put IV', value: ivStr(s.avg_otm_put_iv) },
  ]
  return (
    <div className="bg-forge-card border border-forge-border rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-3">Skew Measures</h3>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        {rows.map((r) => (
          <div key={r.label} className="flex justify-between">
            <span className="text-gray-400">{r.label}</span>
            <span className="text-gray-100 font-mono">{r.value}</span>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-gray-500 mt-3">{s.skew_ratio_description}</p>
    </div>
  )
}
