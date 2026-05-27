'use client'
import type { GexAnalysisData } from '@/lib/gex/types'

export default function FlowDiagnostics({ data }: { data: GexAnalysisData }) {
  return (
    <div className="bg-forge-card border border-forge-border rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-1">Options Flow Diagnostics</h3>
      <p className="text-[11px] text-gray-500 mb-3">{data.flow_diagnostics.note}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {data.flow_diagnostics.cards.map((c) => (
          <div key={c.id} className="rounded-lg border border-gray-800 bg-black/20 p-3">
            <div className="text-sm font-semibold text-white">{c.label}</div>
            <div className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">{c.metric_name}</div>
            <div className="text-lg font-bold text-amber-300">{c.metric_value}</div>
            <div className="text-[11px] text-gray-400 mt-1">{c.description}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
