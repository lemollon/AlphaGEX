'use client'
import type { GexAnalysisData } from '@/lib/gex/types'

// Plain-English glossary of the call-structure classifications the backend emits
// (see core/watchtower_engine.py _classify_call_structure).
const GLOSSARY: { name: string; meaning: string }[] = [
  { name: 'Hedging / Protective', meaning: 'Put activity exceeds calls — portfolio protection / downside hedging.' },
  { name: 'Hedging / Overwrite', meaning: 'Call selling near the money — covered-call / overwriting (caps upside, collects premium).' },
  { name: 'Speculation / Directional', meaning: 'Aggressive far-OTM call buying — leveraged upside bets.' },
  { name: 'Bullish / Accumulation', meaning: 'Net call buying — bullish positioning building.' },
  { name: 'Bullish / Call Dominant', meaning: 'Call volume well above puts (no bid/ask detail available).' },
  { name: 'Balanced / Mixed', meaning: 'No clear directional bias in options flow.' },
  { name: 'Data Unavailable', meaning: 'No volume data — market may be closed.' },
]

export default function CallStructure({ data }: { data: GexAnalysisData }) {
  const detail = data.call_structure_details
  const current = detail?.structure || data.header.call_structure
  return (
    <div className="bg-forge-card border border-forge-border rounded-xl p-4">
      <div className="flex flex-wrap items-baseline gap-3 mb-1">
        <h3 className="text-sm font-semibold text-white">Call Structure</h3>
        <span className="text-amber-300 font-semibold">{current}</span>
        {detail && (
          <span className="text-xs text-gray-500">
            buying pressure {detail.call_buying_pressure.toFixed(3)}
          </span>
        )}
      </div>
      {detail?.description && <p className="text-sm text-gray-300 mb-3">{detail.description}</p>}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
        {GLOSSARY.map((g) => {
          const active = g.name === current
          return (
            <div key={g.name} className="text-[11px] leading-snug">
              <span className={active ? 'text-amber-300 font-semibold' : 'text-gray-400 font-medium'}>{g.name}</span>
              <span className="text-gray-500"> — {g.meaning}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
