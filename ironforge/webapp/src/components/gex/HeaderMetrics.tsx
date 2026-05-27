'use client'
import type { GexAnalysisData } from '@/lib/gex/types'

function fmt(n: number, d = 2): string {
  const a = Math.abs(n)
  if (a >= 1e9) return `${(n / 1e9).toFixed(d)}B`
  if (a >= 1e6) return `${(n / 1e6).toFixed(d)}M`
  if (a >= 1e3) return `${(n / 1e3).toFixed(d)}K`
  return n.toFixed(d)
}

const ratingColor = (r: string) =>
  r === 'BULLISH' ? 'text-green-400' : r === 'BEARISH' ? 'text-red-400' : 'text-gray-300'

export default function HeaderMetrics({ data }: { data: GexAnalysisData }) {
  const h = data.header
  const cells: { label: string; value: string; cls?: string }[] = [
    { label: 'Price', value: h.price.toFixed(2) },
    { label: 'GEX Flip', value: h.gex_flip != null ? h.gex_flip.toFixed(2) : 'N/A', cls: 'text-amber-300' },
    { label: '30-Day Vol', value: h['30_day_vol'] != null ? h['30_day_vol'].toFixed(1) : 'N/A' },
    { label: 'Call Structure', value: h.call_structure, cls: 'text-amber-300' },
    { label: 'Net GEX', value: fmt((h.net_gex || 0) * 1e6, 0) },
  ]
  return (
    <div className="bg-forge-card border border-forge-border rounded-xl p-4 flex flex-wrap items-center justify-between gap-6">
      <div className="flex flex-wrap items-center gap-6">
        {cells.map((c) => (
          <div key={c.label}>
            <div className="text-[11px] uppercase tracking-wide text-gray-500">{c.label}</div>
            <div className={`text-xl font-bold ${c.cls || 'text-white'}`}>{c.value}</div>
          </div>
        ))}
      </div>
      <div className="text-right">
        <div className="text-[11px] uppercase tracking-wide text-gray-500">Rating</div>
        <div className={`text-2xl font-bold ${ratingColor(h.rating)}`}>{h.rating}</div>
        <div className="text-[11px] text-gray-500">Gamma Form: {h.gamma_form}</div>
      </div>
    </div>
  )
}
